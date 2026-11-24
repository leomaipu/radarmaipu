"""Buscador de giros en lenguaje natural: "vendo completos y churrascos" -> Fuente de soda.

Solo sugiere giros; nunca decide si un negocio se puede instalar (eso lo hace el motor de reglas) y el vecino
confirma la sugerencia. Combina dos señales:

- léxica: qué parte de la consulta aparece en las frases del giro (raíces Snowball, sin tildes, ponderadas por
  lo informativa que es cada palabra). No depende de nada externo.
- semántica (opcional): similitud de embeddings entre la consulta y cada frase del giro, calculada por un
  `Embebedor` (puerto). En producción lo implementa Ollama (nucleo/ollama.py); en pruebas, un doble.

Las frases de cada giro salen de giros.json (nombre, sinónimos, palabras de actividad) y de los ejemplos de
buscador_giros.json. Los umbrales y pesos están en buscador_giros.json.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol, Sequence

import snowballstemmer

_STEMMER = snowballstemmer.stemmer("spanish")
_PALABRA = re.compile(r"[a-z0-9ñ]+")


class Embebedor(Protocol):
    """Puerto: convierte textos en vectores. Lanza EmbeddingsNoDisponibles si el servicio no responde."""

    modelo: str

    def embeber(self, textos: Sequence[str]) -> list[list[float]]: ...


class EmbeddingsNoDisponibles(RuntimeError):
    """El servicio de embeddings no respondió o respondió algo inválido."""


@dataclass(frozen=True)
class Sugerencia:
    codigo: str
    nombre: str
    puntaje: float
    lexico: float
    semantico: float | None
    frase: str  # frase del giro que más se parece a la consulta


@dataclass
class Resultado:
    modo: str  # "semantico" | "lexico"
    sugerencias: list[Sugerencia] = field(default_factory=list)


def sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn" or c == "̃").replace("ñ", "ñ")


def raices(texto: str, vacias: frozenset[str]) -> list[str]:
    palabras = [p for p in _PALABRA.findall(sin_tildes(texto)) if p not in vacias]
    return _STEMMER.stemWords(palabras)


def frases_por_giro(giros: dict, cfg_b: dict) -> dict[str, list[str]]:
    """Frases que describen cada giro, sin repetir (sin importar mayúsculas)."""
    ejemplos = cfg_b.get("ejemplos", {})
    salida = {}
    for codigo, g in giros.items():
        actividad = [p.strip().lower() for p in g.get("palabras_actividad") or []]
        candidatas = [g["nombre"], *(g.get("sinonimos") or []), *actividad, *ejemplos.get(codigo, [])]
        vistas, frases = set(), []
        for f in candidatas:
            clave = sin_tildes(f).strip()
            if clave and clave not in vistas:
                vistas.add(clave)
                frases.append(f)
        salida[codigo] = frases
    return salida


def _coseno(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


class IndiceLexico:
    """Cobertura ponderada por IDF de las raíces de la consulta en la bolsa de raíces de cada giro."""

    def __init__(self, frases: dict[str, list[str]], cfg_lex: dict, vacias: frozenset[str]):
        self.cfg, self.vacias = cfg_lex, vacias
        self.bolsas = {c: {r for f in fs for r in raices(f, vacias)} for c, fs in frases.items()}
        n = len(self.bolsas)
        df: dict[str, int] = {}
        for bolsa in self.bolsas.values():
            for r in bolsa:
                df[r] = df.get(r, 0) + 1
        self.idf = {r: math.log(1 + n / d) for r, d in df.items()}
        self.idf_desconocida = math.log(1 + n)  # una palabra que ningún giro usa pesa como la más rara

    def _coincidencia(self, r: str, bolsa: set[str]) -> float:
        if r in bolsa:
            return 1.0
        largo = self.cfg["largo_minimo_prefijo"]
        if len(r) >= largo and any(b.startswith(r) or (len(b) >= largo and r.startswith(b)) for b in bolsa):
            return self.cfg["peso_prefijo"]
        return 0.0

    def puntajes(self, consulta: str) -> dict[str, float]:
        rs = list(dict.fromkeys(raices(consulta, self.vacias)))
        if not rs:
            return {}
        pesos = {r: self.idf.get(r, self.idf_desconocida) for r in rs}
        total = sum(pesos.values())
        return {c: sum(pesos[r] * self._coincidencia(r, b) for r in rs) / total for c, b in self.bolsas.items()}


class IndiceSemantico:
    """Vectores de las frases de cada giro, calculados una vez por modelo y reutilizados entre consultas."""

    def __init__(self, frases: dict[str, list[str]], embebedor: Embebedor, cfg_sem: dict):
        self.frases, self.cfg = frases, cfg_sem
        pref = cfg_sem.get("prefijo_documento", "")
        planas = [(c, f) for c, fs in frases.items() for f in fs]
        textos = [pref + f for _, f in planas]
        lote = cfg_sem["tamano_lote"]
        vectores = [v for i in range(0, len(textos), lote) for v in embebedor.embeber(textos[i:i + lote])]
        if len(vectores) != len(planas):
            raise EmbeddingsNoDisponibles("El servicio devolvió una cantidad distinta de vectores")
        self.vectores: dict[str, list[tuple[str, list[float]]]] = {}
        for (c, f), v in zip(planas, vectores):
            self.vectores.setdefault(c, []).append((f, v))

    def puntajes(self, vector_consulta: Sequence[float]) -> dict[str, tuple[float, str]]:
        salida = {}
        for c, pares in self.vectores.items():
            sim, frase = max(((_coseno(vector_consulta, v), f) for f, v in pares), key=lambda x: x[0])
            salida[c] = (sim, frase)
        return salida


class BuscadorGiros:
    """Fachada del buscador. El índice semántico se construye la primera vez que hay embebedor disponible."""

    def __init__(self, giros: dict, cfg_b: dict, embebedor: Embebedor | None = None):
        self.giros, self.cfg = giros, cfg_b
        self.vacias = frozenset(sin_tildes(p) for p in cfg_b["palabras_vacias"])
        self.frases = frases_por_giro(giros, cfg_b)
        self.lexico = IndiceLexico(self.frases, cfg_b["lexico"], self.vacias)
        self.embebedor = embebedor
        self._semantico: IndiceSemantico | None = None
        self._candado = threading.Lock()

    def consulta_valida(self, consulta: str) -> str | None:
        texto = " ".join((consulta or "").split())[: self.cfg["max_caracteres"]]
        return texto if len(texto) >= self.cfg["min_caracteres"] else None

    def _indice_semantico(self) -> IndiceSemantico:
        with self._candado:
            if self._semantico is None:
                self._semantico = IndiceSemantico(self.frases, self.embebedor, self.cfg["semantico"])
            return self._semantico

    def _mejor_frase_lexica(self, codigo: str, consulta: str) -> str:
        rs = set(raices(consulta, self.vacias))
        return max(self.frases[codigo], key=lambda f: len(rs & set(raices(f, self.vacias))))

    def buscar(self, consulta: str) -> Resultado:
        """Sugerencias ordenadas. Si el embebedor falla, responde en modo léxico (lanza solo si la consulta es vacía)."""
        texto = self.consulta_valida(consulta)
        if texto is None:
            return Resultado(modo="lexico")
        lex = self.lexico.puntajes(texto)
        sem = None
        if self.embebedor is not None:
            try:
                indice = self._indice_semantico()
                [vq] = self.embebedor.embeber([self.cfg["semantico"].get("prefijo_consulta", "") + texto])
                sem = indice.puntajes(vq)
            except (EmbeddingsNoDisponibles, ValueError):
                sem = None
        if sem is not None:
            cs = self.cfg["semantico"]
            filas = [(c, cs["peso_semantico"] * s + cs["peso_lexico"] * lex.get(c, 0.0), lex.get(c, 0.0), s, f)
                     for c, (s, f) in sem.items()]
            umbral, modo = cs["umbral_minimo"], "semantico"
        else:
            filas = [(c, p, p, None, "") for c, p in lex.items()]
            umbral, modo = self.cfg["lexico"]["umbral_minimo"], "lexico"
        filas = sorted((f for f in filas if f[1] >= umbral), key=lambda f: (-f[1], self.giros[f[0]]["nombre"]))
        sugerencias = [
            Sugerencia(codigo=c, nombre=self.giros[c]["nombre"], puntaje=round(p, 4), lexico=round(lx, 4),
                       semantico=None if s is None else round(s, 4),
                       frase=f or self._mejor_frase_lexica(c, texto))
            for c, p, lx, s, f in filas[: self.cfg["max_sugerencias"]]
        ]
        return Resultado(modo=modo, sugerencias=sugerencias)
