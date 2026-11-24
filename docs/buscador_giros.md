# Buscador de giros en lenguaje natural

El vecino describe su negocio ("vendo completos y churrascos") y Radar le sugiere hasta tres giros para que confirme.
Solo sugiere: el veredicto lo sigue dando el motor de reglas.

## Cómo funciona

| Modo | Cuándo | Qué hace |
|---|---|---|
| Léxico | Siempre (sin servicios externos) | Raíces Snowball en español, sin tildes; puntaje = parte de la consulta, ponderada por IDF, presente en las frases del giro |
| Semántico | Con `RM_OLLAMA_URL` y el índice listo | 0,7 × similitud de embeddings (Ollama, local) + 0,3 × léxico |

- Frases de cada giro: nombre, sinónimos y palabras de actividad de `giros.json`, más `ejemplos` de `buscador_giros.json`.
- El índice semántico se arma en segundo plano al iniciar cada proceso; mientras tanto, y si Ollama falla, responde el modo léxico.
- Privacidad: la consulta viaja por POST (no queda en URLs ni en el log de acceso, que además registra solo la ruta) y no se guarda. Pendiente revisar en el servidor el `log-format` de HAProxy: con `option httplog` registra las URL completas de las demás rutas GET (por ejemplo, la búsqueda de direcciones).

## Medición (prototipo, 23-11-2026)

Set: `tests/datos/frases_giros.json`, 100 frases (50 de desarrollo y 50 de prueba, partidas alternando antes de ajustar).

| Buscador | Conjunto | 1.ª sugerencia correcta | Correcta entre las 3 |
|---|---|---|---|
| Filtro actual por texto exacto | prueba | — | 14,3 % |
| Léxico | desarrollo (usado para ajustar) | 93,8 % | 100 % |
| Léxico | prueba | 53,1 % | 63,3 % |
| Semántico | — | por medir en el servidor | por medir |

Advertencias:

- Las frases las escribió la misma persona que ajustó el buscador. El conjunto "prueba" ya se miró una vez, así que dejó de ser ciego.
- La medición honesta requiere un conjunto **nuevo y ciego** de unas 50 frases escritas por funcionarios de Rentas o tomadas de consultas reales. Se pasa con `--frases`.
- Las frases "sin giro" son pocas (2 en desarrollo y 1 en prueba): la tasa de rechazo no es concluyente.

## Activar Ollama en el servidor

1. Desplegar con `RADAR_OLLAMA=si` y la imagen fijada por versión y digest: `RADAR_OLLAMA_IMG=ollama/ollama:X.Y.Z@sha256:...`.
2. El script descarga el modelo una vez (`paraphrase-multilingual`, Apache 2.0, ~0,6 GB), levanta Ollama en la red interna e imprime la medición y la calibración.
3. Elegir `peso_semantico` (y `peso_lexico` = 1 − peso_semantico) y `umbral_minimo` con la tabla de calibración y fijarlos en `config/prc/buscador_giros.json`. Los valores actuales **no están calibrados**. La calibración usa el conjunto `validacion` si viene en el archivo (`--frases`), y si no, desarrollo sin las frases copiadas como ejemplos.
4. Medir con el conjunto ciego de Rentas y registrar el resultado aquí antes de abrir el buscador a los vecinos.
5. Comparar otros modelos sin tocar producción: `python manage.py evaluar_buscador --modelo bge-m3` (con el modelo ya descargado).
