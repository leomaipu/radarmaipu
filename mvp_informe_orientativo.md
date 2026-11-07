# MVP: Informe orientativo de factibilidad (Radar Maipú)

Documento de implementación para Claude Code. Estado: **borrador aprobado en alcance, pendiente de datos documentales** (ver sección 9). No commitear sin instrucción explícita.

## 1. Objetivo

Dado un punto del mapa y un giro de pequeño negocio, producir un **informe orientativo** que indique:

1. la zona normativa del punto según el PRC de Maipú (ZC, ZH o ZI),
2. si el giro es compatible con esa zona, con su condición y artículo de referencia,
3. restricciones o advertencias del entorno (vialidad y riesgos), cuando haya datos verificados,
4. una checklist preliminar de documentos para Rentas, cuando exista lista oficial.

**No es un certificado.** El informe debe decir en todas sus salidas que no reemplaza al
Certificado de Informaciones Previas (CIP) ni a la resolución de la DOM o de Rentas.

## 2. Alcance

Dentro del MVP:
- Consulta punto → zona (capas 2, 3 y 4 de PRCMaipu).
- Matriz zona × giro para ZC y ZH con condición y artículo.
- Modificación N°4 como capa de vigencia separada (ver sección 5).
- Informe JSON y su versión de texto para mostrar en la app.
- Checklist: solo estructura, con los ítems que se carguen desde configuración.

Fuera del MVP:
- Certificado oficial, firma, folio o número de expediente.
- Cálculo de cabida, densidad, altura en m² o estacionamientos por proyecto.
- Comercio cercano (requiere otra fuente).
- Zonas de Industria (ZI-1 a ZI-3) con reglas por giro: la nomenclatura no está resuelta (sección 9).
- Botillerías y giros con alcohol: el resultado es siempre `NO_CONCLUYENTE` hasta cargar la ordenanza de alcoholes (sección 9).

## 3. Fuentes de datos

### 3.1 GIS (MapServer/FeatureServer `MAIPU/PRCMaipu`)

| Capa | Uso en el MVP | Campos usados | Estado |
| --- | --- | --- | --- |
| 2 Zonas Centrales | Zona ZC del punto | `ZONA`, `DESCRIPCION` | Esquema verificado (ZC1 a ZC4) |
| 3 Zonas Uso Preferente Vivienda y Equipamiento | Zona ZH del punto | `ZONA`, `DESCRIPCION`, `ORDENANZA` | Muestra verificada (ZH1 a ZH10); un registro inconsistente (ver 9) |
| 4 Zonas Industriales | Zona ZI del punto | `ZONA`, `DESCRIPCION` | Esquema verificado; nomenclatura en conflicto (ver 9) |
| 0 Vialidad Estructurante | Condición "frente a vía estructurante" | Por confirmar | **Esquema no revisado** |
| 5 Zona BLEVE (AR-4) | Advertencia de riesgo | `ID`, `BUFF_DIST`, `OWNER` | **No usar para decidir** (ver 9) |
| 6 Zonas de Riesgo | Advertencia de riesgo | Por confirmar | **Esquema no revisado** |

Reglas de consulta:
- Consulta espacial punto-polígono: `geometry=<x>,<y>`, `geometryType=esriGeometryPoint`,
  `inSR=4326`, `spatialRel=esriSpatialRelIntersects`, `returnGeometry=false`, `outFields` explícito.
- Usar `outFields` con la lista blanca, nunca `*`.
- Si una capa no responde, el informe marca la sección como `NO_DISPONIBLE`; no falla completo.
- El GIS responde 403 desde el entorno de Claude. Las pruebas en vivo se ejecutan desde la
  red municipal o desde el PC del equipo, como en `scripts/prueba_local.sh`.

### 3.2 Normativa (fuente de la matriz)

- Ordenanza Local del PRC 2004 (Decreto alcaldicio 6383/2004), Capítulo IV, arts. 25 a 41.
- Modificación N°4 (texto aprobatorio, julio 2024; memoria explicativa).

## 4. Modelo de datos (configuración, sin hardcodear)

Carpeta nueva: `config/prc/`.

### 4.1 `config/prc/zonas.json`

Normaliza los códigos del GIS a la nomenclatura de la ordenanza.

```json
{
  "_nota": "ZONA del GIS -> código de ordenanza. Cambiar aquí, no en el código.",
  "normalizacion": { "ZC1": "ZC-1", "ZC2": "ZC-2", "ZC3": "ZC-3", "ZC4": "ZC-4",
                     "ZH1": "ZH-1", "ZH2": "ZH-2", "ZH3": "ZH-3", "ZH4": "ZH-4",
                     "ZH5": "ZH-5", "ZH6": "ZH-6", "ZH7": "ZH-7", "ZH8": "ZH-8",
                     "ZH9": "ZH-9", "ZH10": "ZH-10" },
  "zonas_excluidas_mvp": ["ZI-1", "ZI-2", "ZI-3"]
}
```

### 4.2 `config/prc/usos_comercio.json`

Matriz de la clase 2.2 Comercio por zona. Cada entrada cita artículo y página de la ordenanza.

Forma de cada zona:

```json
{
  "ZH-6": {
    "fuente": "Ordenanza PRC 2004, art. 34, Cuadro usos de suelo, p. 27",
    "vivienda": "SI",
    "hospedaje": "SI",
    "comercio": {
      "escalas": { "basico": "SI", "menor": "CONDICION", "mediano": "CONDICION" },
      "condicion_escala": { "menor": "vialidad_estructurante", "mediano": "vialidad_estructurante" },
      "prohibido": ["distribucion_venta_carbon_lena", "materiales_construccion",
                    "automoviles", "discotecas", "cabaret", "boite"],
      "talleres_vias_20m": ["taller_mecanico", "pinturas", "vulcanizacion", "imprentas"]
    }
  }
}
```

Contenido verificado en la ordenanza (no inventar lo que falte):

| Zona | Vivienda | Hospedaje | Comercio: escalas | Prohibiciones de comercio (extracto) | Notas |
| --- | --- | --- | --- | --- | --- |
| ZC-1 | NO | NO | básico, menor, mediano | botillerías, pollos asados, fuentes de soda, bar, pub, repuestos automotor, supermercado, carbón/leña, gas licuado, discotecas, cabaret, boite | Centro Cívico |
| ZC-2 | SI (sin 1.er piso frente a Av. 5 de Abril y Pajaritos) | SI | básico, menor, mediano | carbón, leña, materiales, gas licuado, estaciones de servicio; cabaret/boite no frente a Av. 5 de Abril | Altura Mod. 4 (ver 5) |
| ZC-3 | SI | SI | básico, menor, mediano | carbón, leña; cabaret/boite no frente a Av. 5 de Abril ni en ICH/monumentos; no en Camino a Rinconada ni Carmen | Apart hotel prohibido (Mod. 4) |
| ZC-4 | SI (máx. 55 % de la superficie) | SI | todas | (sin prohibiciones de escala en la tabla) | Apart hotel prohibido (Mod. 4) |
| ZH-1 | SI | SI | **no confirmado** (texto superpuesto) | — | Revisar original |
| ZH-2 | SI | SI, sin comercio adjunto | básico, menor | repuestos, automóviles, centro comercial, mercado, supermercado, multitiendas, compra/venta automóviles y maquinarias, carbón, leña, materiales, centro/estación de servicio, revisión técnica, gas licuado, centros de copiado, discotecas, cabaret, boite | — |
| ZH-3 | SI | NO | básico, mediano; menor solo en vía estructurante | repuestos, carbón, leña, materiales, automóviles y maquinarias, discotecas, cabaret, boites | — |
| ZH-4 | SI | SI | básico, menor, mediano | discotecas, cabaret, boites | Esparcimiento y salud menor solo en vía estructurante |
| ZH-5 | SI | SI, sin motel | básico, menor, mediano | carbón, leña, discotecas, cabaret, boites | Talleres solo en vías de 20 m o más |
| ZH-6 | SI | SI, sin comercio adjunto | básico; menor y mediano solo en vía estructurante | carbón, leña, materiales, automóviles, discotecas, cabaret, boites | Talleres solo en vías de 20 m o más |
| ZH-7 | SI | SI, sin comercio adjunto | básico; menor y mediano solo en vía estructurante | carbón, leña, materiales, automóviles, maquinarias, discotecas, cabaret, boites | Talleres solo en vías de 20 m o más |
| ZH-8 | SI | SI | básico, menor, mediano | carbón, leña; talleres mecánico, pinturas y vulcanización prohibidos | Verificar lectura; apart hotel prohibido (Mod. 4) |
| ZH-9 | SI | SI | básico, menor, mediano | carbón, leña, materiales, automóviles, cabaret, boites | Talleres solo en vías de 20 m o más |
| ZH-10 | SI | SI | básico, menor, mediano | carbón, leña, materiales, automóviles, maquinarias, cabaret, boites | Apart hotel prohibido (Mod. 4) |
| ZI-1 a ZI-3 | Solo cuidador | NO | menor, mediano, mayor | (sin revisar) | Excluida del MVP |

Notas de la matriz:
- Las escalas (básico, menor, mediano, mayor) se definen en el **art. 2.1.36 OGUC**, que no está
  cargado. Hasta cargarlo, todo comercio que dependa de escala devuelve `CONDICION` con la nota
  "escala por definir".
- "Restaurante y similares" y "bazar", "abarrotes", "panadería (solo venta)" están listados en 2.2.
- Estacionamiento de restaurantes: 1 cada 30 m² de superficie útil (tabla de art. 22/23).

### 4.3 `config/prc/modificaciones.json`

Capa de vigencia. Cada modificación tiene su estado y solo se aplica si `vigente` es `true`.

```json
{
  "PRC_2004": { "vigente": true, "decreto": "6383/2004", "publicacion_do": "2004-11-13" },
  "MOD_4": {
    "vigente": false,
    "motivo": "Texto aprobatorio y memoria recibidos; falta número de decreto y publicación en Diario Oficial",
    "decreto": null,
    "publicacion_do": null,
    "zonas": ["ZC-2", "ZC-3", "ZC-4", "ZH-8", "ZH-10"],
    "alturas": {
      "ZC-2": { "continua_y_aislada": "4 pisos / 12 m", "solo_continua": "sin cambio en texto aprobado (ver 9)" },
      "ZC-3": { "vivienda_multifamiliar_equip_otras": "8 pisos / 24 m" },
      "ZC-4": { "equip_todas_y_multifamiliar": "9 pisos / 27 m" },
      "ZH-8": { "equip_todas_y_multifamiliar": "9 pisos / 27 m" },
      "ZH-10": { "vivienda_equip_condicionado": "6 pisos / 18 m" }
    },
    "apart_hotel_prohibido": ["ZC-3", "ZC-4", "ZH-8", "ZH-10"],
    "incentivos_zonas": ["ZC-2", "ZC-3", "ZC-4", "ZH-8"]
  }
}
```

Regla: el informe usa `PRC_2004` como base. Si `MOD_4.vigente` es `true`, reemplaza las alturas
y aplica la prohibición de apart hotel. Mientras sea `false`, el informe lo indica en una
advertencia ("modificación aprobada, vigencia por confirmar").

### 4.4 `config/prc/vialidad.json` (pendiente)

Umbrales de la vía del frente: 15 m y 20 m, y la marca de "vía estructurante". Se completa
cuando se revise el esquema de la capa 0.

## 5. Reglas de evaluación

Para cada par (zona, giro) el resultado es uno de:

| Estado | Significado |
| --- | --- |
| `PERMITIDO` | Compatible sin condición. |
| `PERMITIDO_CON_CONDICION` | Compatible si se cumple la condición (escala, vía, frente). Se muestra cuál. |
| `NO_PERMITIDO` | Prohibido en la matriz o por el uso de suelo. |
| `NO_CONCLUYENTE` | No hay dato suficiente (zona fuera de la matriz, giro con alcohol, dato sin verificar). |

Orden de evaluación:

1. Punto fuera del área urbana o sin zona en capas 2, 3 y 4 → `NO_CONCLUYENTE`, motivo "fuera de zona normativa".
2. Zona fuera de `usos_comercio.json` → `NO_CONCLUYENTE`.
3. Giro en la lista de prohibidos de la zona → `NO_PERMITIDO`, con artículo.
4. Giro con alcohol → `NO_CONCLUYENTE` (motivo: "requiere ordenanza de alcoholes y Ley 19.925").
5. Giro con condición de escala → `PERMITIDO_CON_CONDICION`, con la nota de la escala.
6. Giro con condición de vía (estructurante, 15 m, 20 m):
   - si la capa 0 responde: evaluar;
   - si no: `PERMITIDO_CON_CONDICION` con la nota "verificar frente a vía estructurante".
7. Advertencias de riesgo (capas 5 y 6): se agregan como `advertencias`; no cambian el estado,
   salvo que se validen las fuentes (sección 9).
8. Modificación N°4: se aplica solo si `vigente` es `true` (sección 4.3).

## 6. Salida: informe orientativo

### 6.1 JSON

```json
{
  "version_informe": "0.1",
  "fecha_generacion": "2026-11-09T10:00:00-03:00",
  "punto": { "lat": -33.5102, "lon": -70.7535 },
  "zona": { "gis": "ZH6", "ordenanza": "ZH-6", "descripcion": "..." },
  "giro": { "codigo": "bazar", "clase_ordenanza": "2.2 Comercio", "escala": null },
  "resultado": {
    "estado": "PERMITIDO_CON_CONDICION",
    "motivo": "Comercio básico permitido. Escala menor solo en vía estructurante.",
    "articulo": "Art. 34, ZH-6"
  },
  "advertencias": [
    { "tipo": "vialidad", "texto": "Verificar si el frente da a vía estructurante." },
    { "tipo": "normativa", "texto": "Escala por definir: art. 2.1.36 OGUC no cargado." }
  ],
  "fuentes": [
    { "titulo": "Ordenanza PRC 2004", "pagina": 27 },
    { "titulo": "Modificación N°4", "vigente": false }
  ],
  "checklist_rentas": { "estado": "pendiente_lista_oficial", "items": [] },
  "aviso": "Informe orientativo. No reemplaza el Certificado de Informaciones Previas ni la resolución de la DOM o de Rentas."
}
```

### 6.2 Texto para la app

Mismo contenido en tres bloques: zona, resultado del giro, advertencias. El aviso debe
aparecer siempre, en la parte visible y no en un enlace.

## 7. Endpoints (propuesta)

- `GET /api/informe?lat=&lon=&giro=` → informe JSON.
- `GET /api/giros` → lista de giros soportados con su clase de ordenanza.
- `GET /api/health` → ya existe; agregar estado de carga de las capas PRC.

El giro se valida contra `config/prc/giros.json` (nuevo). No aceptar texto libre sin
normalizar.

## 8. Pruebas

Obligatorias, en `tests/test_informe.py` y `tests/test_usos.py`:

1. Normalización de zonas: `ZH1` → `ZH-1`, `ZC4` → `ZC-4`.
2. ZC-1 + botillería → `NO_CONCLUYENTE` (alcohol), no `PERMITIDO`.
3. ZH-2 + discoteca → `NO_PERMITIDO`.
4. ZH-6 + bazar sin dato de vía → `PERMITIDO_CON_CONDICION`, con advertencia de vía.
5. ZH-6 + bazar con vía estructurante verificada → `PERMITIDO`, escala por definir.
6. ZI-1 + cualquier giro → `NO_CONCLUYENTE` (fuera del MVP).
7. Mod. 4 con `vigente: false` → alturas base y advertencia de vigencia.
8. Mod. 4 con `vigente: true` → ZH-8 altura 9 pisos / 27 m y apart hotel prohibido en ZH-8.
9. ZC-2 con "solo continua" → sin cambio de altura (según texto aprobatorio).
10. Capa no disponible → informe con sección `NO_DISPONIBLE`, sin excepción.
11. Privacidad: ninguna respuesta incluye RUT, razón social, representante ni `direc_nego`.
12. Punto sin zona → `NO_CONCLUYENTE`, motivo "fuera de zona normativa".

Las pruebas que consultan el GIS en vivo van marcadas `@pytest.mark.gis` y no corren por defecto.

## 9. Pendientes que bloquean partes del MVP

| # | Pendiente | Consecuencia si no se resuelve | Responsable sugerido |
| --- | --- | --- | --- |
| 1 | Número y fecha de publicación en el Diario Oficial de la Mod. 4 | Mod. 4 queda `vigente: false` | DOM / Secplan |
| 2 | Art. 2.1.36 OGUC (escalas) | Escala siempre `CONDICION` | Asesoría Urbana |
| 3 | Ordenanza municipal de alcoholes y Ley 19.925 | Botillerías y alcohol `NO_CONCLUYENTE` | Jurídico / Rentas |
| 4 | Lista oficial de documentos de Rentas por patente | Checklist vacía | Rentas |
| 5 | Confirmar DOM: ¿emite certificado de zonificación por giro o solo CIP? | Define el nombre del producto y su texto | DOM |
| 6 | Esquema de capas 0 y 6 (campos de vía y riesgo) | Sin condición de vía ni riesgo verificado | SITMA |
| 7 | Fuente de BUFF_DIST (800/400 m) y OWNER ("SDE", "URBANA") de la capa 5; X/Y de relleno (0,0) | Capa 5 no se usa para decidir | SITMA |
| 8 | Capa 5 con geometría (GeoJSON) | No hay geometría para intersectar | SITMA |
| 9 | Conflicto ZI: GIS ZI1 "Exclusiva", ZI2 "Inofensiva (de transición)", ZI3 "Peligrosa (Combustibles)" vs. plano 1A "ZI-2 Transición Oriente" y "ZI-3 Transición Poniente" | ZI excluidas del MVP | Planificación |
| 10 | Registro de capa 3 con `ZONA = ZH10` y `DESCRIPCION = "Zona Habitacional 9: El Porvenir"` | Riesgo de zona mal asignada | Planificación |
| 11 | Mod. 4 tabla 10 asigna incentivo a ZH-10; el texto aprobatorio lo excluye | Se sigue el texto aprobatorio | DOM (confirmar) |
| 12 | Mod. 4 tabla 12 muestra 4 pisos/12 m también para ZC-2 "solo continua"; el texto solo cambia "continua y aislada" | Se sigue el texto aprobatorio | DOM (confirmar) |
| 13 | Página del plan regulador llama "Centro Cívico" a ZC2; la ordenanza lo llama ZC-1 | Se sigue la ordenanza | Informar a Asesoría Urbana |
| 14 | ZH-1 y ZH-8: lectura de comercio parcial en las imágenes | Verificar antes de producción | Revisar PDF original |

## 10. Criterios de aceptación del MVP

- Para un punto dentro de ZC o ZH, el informe devuelve zona normativa y un estado para cada
  giro de la lista.
- Ningún resultado de botillería o de alcohol da `PERMITIDO` mientras el pendiente 3 esté abierto.
- Todo informe incluye el aviso y la lista de fuentes con página.
- Las pruebas de la sección 8 pasan en local sin GIS, y las marcadas `gis` pasan desde la red municipal.
- Ninguna salida incluye datos personales de patentes.

## 11. Fuera de este documento

Este documento no autoriza commits, push ni cambios de configuración de producción. Esos pasos
se hacen cuando el equipo lo pida.
