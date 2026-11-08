# MVP: Informe orientativo de factibilidad (Radar Maipú)

Documento de implementación para Claude Code.

- **Versión:** 0.3 (2026-11-08). Reemplaza la 0.2.
- **Estado:** informe implementado (PR #3). Migración a Django y vista de mapa implementadas en la rama `feature/django-mapa` (secciones 12 y 13).
- **Commits:** este documento no autoriza commits, push ni cambios en producción. Esos pasos se hacen cuando el equipo los pida.

## 1. Objetivo

Dado un punto del mapa y un giro de pequeño negocio, el informe orientativo indica:

1. la zona normativa del punto según el PRC de Maipú;
2. si el giro es compatible con esa zona, con su condición y el artículo de referencia;
3. las restricciones del entorno: vialidad, áreas de riesgo y Modificación N°4;
4. una checklist preliminar de documentos para Rentas, cuando exista la lista oficial;
5. el comercio cercano (patentes vigentes), a partir de la iteración 2.

**No es un certificado.** Todas las salidas deben decir que el informe no reemplaza al Certificado de Informaciones Previas (CIP) ni a la resolución de la DOM o de Rentas.

## 2. Alcance

| Funcionalidad | Estado |
| --- | --- |
| Punto → zona (capas 1 a 4) | Hecho |
| Matriz zona × giro para ZC-1 a ZC-4 y ZH-1 a ZH-10: comercio (2.2), servicios artesanales (2.10) y hospedaje (1.2) | Hecho |
| Modificación N°4 como capa de vigencia | Hecho; vigente |
| Advertencias de vialidad (capa 0) y riesgo (capas 5 y 6) | Hecho |
| Informe en JSON y en texto | Hecho |
| Checklist de Rentas | Editable en `/admin`; vacía hasta que Rentas la entregue |
| Vista de mapa que consuma la API | Hecho (iteración 2) |
| Comercio cercano en el informe | Hecho: `comercio_cercano` en el informe |
| Zonas industriales ZI-1 a ZI-3 | Fuera del MVP. Dan `NO_CONCLUYENTE` |
| Giros con alcohol | `NO_CONCLUYENTE` hasta cargar la ordenanza de alcoholes, salvo que la zona los prohíba (entonces `NO_PERMITIDO`) |
| Certificado oficial, cálculo de cabida, estacionamientos por proyecto | Fuera del alcance |

## 3. Fuentes de datos

### 3.1 GIS: servicio `MAIPU/PRCMaipu` (MapServer)

Todos los esquemas están verificados en vivo (2026-11-07).

| Capa | Uso | Campos (lista blanca) | Notas |
| --- | --- | --- | --- |
| 0 Vialidad Estructurante (polilíneas) | Frente probable y vías de 20 m | `JERARQUIA, VIA, CODIGO, ANCHO_EXIS, ANCHO_PROP, OBSERVACIO, MODIFICACI, OBSERVACION_2` | Trae tramos proyectados ("APERTURA", también escrito "Aeertura") y eliminados: se excluyen. Hay 82 tramos con `ANCHO_EXIS` vacío y valores raros como "140" o "Sin solera" |
| 1 Zonas de Uso Especial | ZE-1 a ZE-12, ICH, ZCH | `ZONA, DESCRIPCION` | No estaba en la versión 0.1. Hay al menos 1 polígono ZE-8 sobre ZH-6 |
| 2 Zonas Centrales | ZC-1 a ZC-4 | `ZONA, DESCRIPCION` | |
| 3 Zonas Uso Preferente Vivienda y Equipamiento | ZH-1 a ZH-10 | `ZONA, DESCRIPCION` | Un registro `ZH10` tiene la descripción de ZH-9 (pendiente 10) |
| 4 Zonas Industriales | ZI-1 a ZI-3 | `ZONA, DESCRIPCION` | Hoy dice ZI1 "Exclusiva", ZI2 "Transición Oriente", ZI3 "Transición Poniente" |
| 5 Zona BLEVE (AR-4) | Advertencia | `BUFF_DIST` | Tiene geometría (2 polígonos, 800 y 400 m). La fuente de la distancia sigue sin validar |
| 6 Zonas de Riesgo | Advertencia | `TIPO_DE_AR, DESCRIPCIO` | AR-1A, AR-1B, AR-1C, AR-2, AR-3, AR-4, AR-6B |

Reglas de consulta:
- Consulta punto-polígono con `geometry=<lon>,<lat>`, `inSR=4326` y `esriSpatialRelIntersects`.
- `outFields` es una lista blanca **por capa**. Pedir un campo que la capa no tiene hace fallar la consulta con error 400.
- Si una capa de zonas falla, la zona queda `NO_DISPONIBLE` y el resultado es `NO_CONCLUYENTE`: con una capa caída no se puede descartar una zona superpuesta. Si falla vialidad o riesgo, solo esa sección queda `NO_DISPONIBLE`.
- Cerca del 25 % de los puntos no cae en ninguna zona, porque quedan en la vía pública o fuera del límite urbano. En ese caso el informe sugiere las zonas a menos de 30 m.
- El GIS responde desde el PC del equipo, donde corren las pruebas marcadas `gis`.
- El servicio también entrega la imagen renderizada (`/export`) y la leyenda (`/legend`), sin teselas cacheadas. Sirve para mostrar el PRC en el mapa con la simbología oficial (sección 12).

### 3.2 Normativa

| Fuente | Uso | Ubicación |
| --- | --- | --- |
| Ordenanza Local PRC 2004 (D.A. 6383/2004), arts. 25, 28-32, 34, 41, capítulo V de riesgos y arts. 48-51 de vialidad | Matriz, arts. 30, 31 y 32, riesgos y vialidad | PDF del decreto. Las páginas citadas son las del PDF |
| Diario Oficial 13-11-2004 | Texto legible de ZH-1 (p. 6) y verificación de ZH-8 (p. 8) | PDF de la publicación |
| Modificación N°2 (D.A. 6971/2012) | Según su texto aprobatorio, no reemplaza las filas 2.2, 2.10 ni 1.2 de ZC/ZH. Renumeró los artículos 47-50 | BCN LeyChile, idNorma 1045540. Sus tablas son imágenes, así que no están contrastadas |
| Modificación N°4 (D.A. 5.664 de 10-09-2024, DO N° 43.950 de 13-09-2024, CVE 2545334) | Alturas, prohibición de apart hotel, incentivos | Diario Oficial y texto aprobatorio |

## 4. Modelo de datos (configuración en `config/prc/`)

| Archivo | Contenido |
| --- | --- |
| `zonas.json` | Normaliza códigos GIS a la ordenanza (`ZH1` → `ZH-1`, incluye ZE, ICH y ZCH); zonas excluidas; descripción de las zonas especiales del art. 41; capas y `outFields` |
| `usos_comercio.json` | Matriz por zona: escalas (`SI`, `NO`, `CONDICION`), condición de escala, prohibidos, `solo_giros`, condición por giro, condiciones en texto, servicios artesanales, hospedaje y página de la fuente |
| `giros.json` | 63 giros con clase (2.2, 2.10 o 1.2), si llevan alcohol, nota y condición general (arts. 30 y 31 para estación de servicio, revisión técnica y gas licuado; escala grande para supermercado y similares) |
| `modificaciones.json` | PRC 2004, Mod. N°2 (informativa) y Mod. N°4 con su decreto, publicación, alturas, zonas con apart hotel prohibido y zonas con incentivos |
| `alturas.json` | Altura máxima base por zona y por condición de edificación |
| `vialidad.json` | Jerarquías estructurantes, jerarquías "colectora o mayor", exclusión de tramos, radio de búsqueda y margen de frente |
| `riesgos.json` | Texto de advertencia por tipo de área de riesgo y para la zona BLEVE |
| `checklist_rentas.json` | `pendiente_lista_oficial`, sin ítems |

Correcciones a la matriz de la versión 0.1, verificadas contra las fuentes:

- **ZH-1:** comercio solo en escalas **menor y mediana** (sin básica). La menor va solo frente a una vía colectora o de mayor jerarquía, y en vías de servicio solo se permiten restaurante y pub de escala menor. Las prohibiciones vienen del Diario Oficial, p. 6.
- **ZH-8:** comercio en **todas las escalas**; solo prohíbe carbón y leña. En servicios artesanales prohíbe pintura y desabolladura y vulcanización, pero **no** el taller mecánico.
- **ZH-4:** el hospedaje se limita a residencial, hostal u hospedería sin servicios comerciales adjuntos.
- **Talleres:**
  - En ZH-5, ZH-6, ZH-7, ZH-9 y ZH-10, el taller mecánico, de pintura, de vulcanización y la imprenta van solo en vías de 20 m o más.
  - En ZH-4, todos los talleres van solo en vialidad estructurante.

## 5. Reglas de evaluación

Estados posibles: `PERMITIDO`, `PERMITIDO_CON_CONDICION`, `NO_PERMITIDO` y `NO_CONCLUYENTE`.

Orden de evaluación (implementado en `app/usos.py`):

1. **Zona.**
   - Sin zona → `NO_CONCLUYENTE`, "fuera de zona normativa".
   - Capa de zonas caída → `NO_CONCLUYENTE`.
   - Zona ZI → `NO_CONCLUYENTE` (fuera del MVP).
   - ZE, ICH o ZCH → `NO_CONCLUYENTE` (art. 41).
2. **Prohibición de la zona** (también `solo_giros` y la Mod. N°4 para apart hotel) → `NO_PERMITIDO`.
3. **Alcohol** → `NO_CONCLUYENTE`, con la nota del art. 28.
4. **Escalas.**
   - Si el usuario declara una escala, se evalúa solo esa.
   - Si no la declara, se evalúan básica, menor y mediana: `PERMITIDO` solo si las tres lo son; `NO_PERMITIDO` si ninguna; en cualquier otro caso, `PERMITIDO_CON_CONDICION`.
   - Siempre se advierte "escala por definir" mientras no se cargue el art. 2.1.36 de la OGUC.
5. **Condiciones de vía** (`vialidad_estructurante`, `colectora_o_mayor`, `via_20m`).
   - Se cumplen solo con un **frente confirmado**.
   - La cercanía al eje marca un "frente probable" pero no habilita nada.
   - El usuario confirma el frente repitiendo la consulta con `frente_via=<CODIGO>`, y solo si esa vía es un frente probable construido.
   - La regla de 20 m usa solo el ancho existente; un ancho mayor a 100 m se descarta por implausible.
   - La ausencia de datos nunca convierte una condición en `NO`.
6. **Condiciones en texto** (por zona o generales del giro): bajan un `PERMITIDO` a `PERMITIDO_CON_CONDICION`.
7. **Riesgos y BLEVE:** se agregan como advertencias y no cambian el estado.
8. **Calidad del dato:** si la descripción del GIS no coincide con el código de zona, se evalúan ambas zonas. Si los resultados difieren → `NO_CONCLUYENTE`.
9. **Art. 32:** si el estado no es `PERMITIDO` y la zona admite vivienda, se informa que el pequeño comercio dentro de una vivienda se permite en cualquier zona, mientras la vivienda siga siendo el destino principal.

**Desviación aprobada por revisión respecto de la versión 0.1:** ZC-1 + botillería da `NO_PERMITIDO` y no `NO_CONCLUYENTE`, porque la prohibición de la zona se evalúa antes que el alcohol. Ningún giro con alcohol da `PERMITIDO`.

## 6. Salida

### 6.1 JSON

Mantiene las claves de la versión 0.1 y agrega estas:

- `zona.cercanas`
- `zona.capas_fallidas`
- `giro.nombre`
- `frente_declarado`
- `resultado.detalle_escalas`
- `edificacion` (altura máxima vigente y estado de la Mod. N°4)
- `vialidad` (vías cercanas, frente probable o confirmado, tramos excluidos)
- `riesgos`
- `secciones` (estado de cada bloque: `OK` o `NO_DISPONIBLE`)

Tipos de advertencia: `vialidad`, `normativa`, `condicion`, `riesgo`, `calidad_dato`, `ubicacion`, `giro` y `gis`.

### 6.2 Texto para la app

`formato=texto` entrega el aviso al inicio y al final, y entre ambos tres bloques: zona (con alturas), resultado del giro y advertencias, más las fuentes.

## 7. Endpoints (implementados)

- `GET /api/informe?lat=&lon=&giro=[&escala=basico|menor|mediano|mayor][&frente_via=CODIGO][&formato=json|texto]`. El giro se valida contra `giros.json`; un código desconocido devuelve 422.
- `GET /api/giros`: código, nombre, clase y si requiere la ordenanza de alcoholes.
- `GET /api/health`: agrega `prc` con el estado de la configuración, `mod4_vigente` y la última respuesta de cada capa.
- Existentes y reutilizables en el mapa:
  - `/api/punto` (comercio cercano: patentes vigentes en un radio)
  - `/api/patentes` (por área)
  - `/api/direccion` y `/api/buscar-direccion` (geocodificador)
  - `/api/calles` y `/api/barrios`

## 8. Pruebas

- **`tests/test_usos.py` y `tests/test_informe.py`:** 191 pruebas pasan en local sin GIS. Cubren:
  - las 12 pruebas de la versión 0.1 (la prueba 2 según la desviación de la sección 5);
  - frentes probables y declarados;
  - tramos excluidos;
  - respuestas malformadas del GIS;
  - el art. 32;
  - la integridad de los códigos en la configuración.
- **Marcadas `gis`:** 2 pruebas en vivo, también verdes. Se corren con `pytest -m gis`.
- **Revisión adversarial:** en la ronda 1 encontró 2 bloqueantes (frente por proximidad y vías no construidas; ZH-1 en escala mediana), ya corregidos. La ronda 2 dio "aprobado"; sus 4 observaciones también se corrigieron.

## 9. Pendientes

| # | Pendiente | Estado | Responsable sugerido |
| --- | --- | --- | --- |
| 1 | Decreto y publicación de la Mod. N°4 | **Resuelto:** D.A. 5.664/2024, DO 13-09-2024 | — |
| 2 | Art. 2.1.36 OGUC (escalas por carga de ocupación) | Abierto. Toda respuesta dice "escala por definir" | Asesoría Urbana |
| 3 | Ordenanza municipal de alcoholes y Ley 19.925 | Abierto | Jurídico / Rentas |
| 4 | Lista oficial de documentos de Rentas | Abierto. Checklist vacía | Rentas |
| 5 | ¿La DOM emite certificado de zonificación por giro o solo CIP? | Abierto | DOM |
| 6 | Esquema de las capas 0 y 6 | **Resuelto** (sección 3.1) | — |
| 7 | Fuente de `BUFF_DIST` (800/400 m) de la capa 5 | Abierto. Solo informativo | SITMA |
| 8 | Geometría de la capa 5 | **Resuelto:** tiene geometría | — |
| 9 | Nomenclatura ZI | **Resuelto en el GIS**; las ZI siguen fuera del MVP | — |
| 10 | Registro `ZH10` con descripción de ZH-9 | Abierto. Mitigado por la regla 8 | Planificación / SITMA |
| 11 | Incentivos de ZH-10 (tabla 10 vs. texto aprobatorio) | Se sigue el texto aprobatorio | DOM (confirmar) |
| 12 | Altura de ZC-2 "solo continua" | Se sigue el texto aprobatorio (sin cambio) | DOM (confirmar) |
| 13 | "Centro Cívico" (ZC2 en la web vs. ZC-1 en la ordenanza) | Se sigue la ordenanza | Asesoría Urbana |
| 14 | Lectura de ZH-1 y ZH-8 | **Resuelto** con el Diario Oficial 2004 | — |
| 15 | ¿Las vías de servicio y locales son "vialidad estructurante del PRC"? (art. 51 vs. art. 48) | **Nuevo.** Hoy cuentan, y se advierte | DOM |
| 16 | Tablas de la Mod. N°2 (son imágenes) | **Nuevo.** Contrastar contra el expediente | Asesoría Urbana |
| 17 | Tramos de la capa 0 con `ANCHO_EXIS` vacío o implausible | **Nuevo** | SITMA |
| 18 | Superposición ZE-8/ZH-6 en la capa 1 | **Nuevo.** Hoy da `NO_CONCLUYENTE` | SITMA |

## 10. Criterios de aceptación del MVP

Todos se cumplen:

- Un punto dentro de ZC o ZH devuelve la zona y un estado para cada giro.
- Ninguna botillería ni giro con alcohol da `PERMITIDO`.
- Todo informe incluye el aviso y las fuentes con página.
- Las pruebas pasan en local, y las marcadas `gis` pasan desde el PC del equipo.
- Ninguna salida trae datos personales de patentes.

## 11. Iteración 2: alcance propuesto

1. **Vista de mapa** que consuma la API:
   - buscar una dirección o hacer clic;
   - elegir el giro;
   - ver el informe y las capas del PRC con su simbología oficial;
   - ver el comercio cercano agrupado.
2. **Comercio cercano en el informe:** patentes vigentes en un radio, separando las de giro similar. Hay que mapear `giro` a palabras de `actividad`, porque `actividad` es texto libre. Solo se usan los campos de la lista blanca de `app/privacy.py`.
3. **Checklist de Rentas:** cuando llegue la lista, solo se edita la configuración (o el panel de administración, si se adopta Django).
4. **Almacenamiento:** pasar del almacén en memoria a PostGIS (ya era requisito para producción según el README).

## 12. Vista de mapa: requisitos

- Funcionar en celulares (portal web progresivo) y en escritorio.
- Mapa base: OpenStreetMap o mapa base municipal.
- Capa del PRC: imagen del `/export` del MapServer, con leyenda desde `/legend`.
- Interacción:
  - clic o búsqueda de dirección (`/api/buscar-direccion`);
  - selección de giro (`/api/giros`);
  - informe (`/api/informe`), con el botón "mi predio enfrenta esta vía" que reenvía la consulta con `frente_via`.
- Patentes: unas 12.400, y más de 300 en 150 m en el centro, así que hace falta agruparlas en el mapa.
- El aviso del informe siempre visible en el panel, no en un enlace.

## 13. Stack tecnológico (decidido el 2026-11-07)

- **Backend:** Django 5.2 LTS + GeoDjango + PostGIS, con la API en Django Ninja (mismas rutas `/api/...` que la versión FastAPI). El motor normativo (`nucleo/`) sigue siendo Python puro.
- **Interfaz:** plantillas Django + Leaflet + HTMX, mobile first, PWA y manual de marca municipal (Rubik; paleta #10174A, #33CCCC, #E60380, #FFB71B, #575CA4, #FFB3C0).
- **Panel de administración:** checklist de Rentas editable (`tramites`), bitácora de cargas del GIS y consulta de patentes en solo lectura.
- **Ejecución:** contenedores (podman o docker compose).

Hallazgos de esta iteración:

- CARTO ahora exige clave para sus mosaicos. Se usa el lienzo gris de Esri más la cartografía municipal (`MAIPU/BaseMaipu`) a nivel de calle.
- La **leyenda** oficial del PRC todavía rotula ZI2 como "Inofensiva" y ZI3 como "Peligrosa", aunque los polígonos dicen "Transición Oriente/Poniente" (pendiente 9 sigue abierto en la simbología).
- El GIS publica capas de predios (`DOM/PREDIOS_*`, `MAIPU/BaseMaipu` capa 2). Con ellas se podría verificar el frente del local de verdad en una próxima iteración.
