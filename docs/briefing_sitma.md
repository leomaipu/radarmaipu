# Radar Maipú: qué consultamos al GIS y para qué

Documento para el equipo SITMA. Describe las consultas que hará el MVP, las capas
involucradas y lo que necesitamos confirmar.

## Qué hace el MVP

El portal muestra un mapa. Al tocar un punto, el sistema responde:
- la calle más cercana (nombre y tipo),
- las patentes comerciales vigentes en un radio, con su tipo y estado,
- la restricción o estado de cada patente, cuando corresponda.

Es una herramienta de orientación para quien evalúa instalar un negocio. No reemplaza
la decisión municipal ni la tramitación en Rentas.

## Capas que consumimos

| Capa | Servicio | Uso |
| --- | --- | --- |
| Calles | DOM/DOM_CATASTRO_MUNICIPAL/FeatureServer/1 | Nombre, tipo (`CLASE`), búsqueda y calle cercana |
| Patentes | DAF/PATENTES_2026_2/FeatureServer (capas 0, 1 y 2) | Puntos de patentes, estado y subtipo |
| Barrios | MAIPU/LimitesBarrios | Barrio del punto (pendiente de implementar) |
| Geocodificación | BETA/LocatorBetaV3dot3/GeocodeServer | Ver sección siguiente |

Campos que **no** pedimos al servidor: RUT, razón social, representante, dirección
personal y código SII. Esto se aplica en la consulta misma, no solo en nuestra base.

## Uso del geocodificador (BETA/LocatorBetaV3dot3)

**Verificado (2026-11-03):** el servicio responde en JSON, versión 11.3. Sus campos de
dirección son `Address` ("Dirección o lugar"), `Address2`, `Address3` y `Neighborhood`
("Barrio"), todos texto. La operación `findAddressCandidates` acepta, entre otros,
`SingleLine`, `Max Locations`, `Category`, `Location Type`, `Source Country`, `Magic Key`
y `Out Fields`.

**Verificado desde el PC del equipo (2026-11-03):** `reverseGeocode` funciona. Con el punto
`x=-70.7535, y=-33.5102` (WGS84) devolvió la dirección `0260 5 DE ABRIL`, con
`Addr_type = PointAddress`, `Neighborhood = MAIPU CENTRO` y `City = MAIPÚ`.

Observaciones para el diseño:
- La respuesta vino en EPSG:32719 (UTM 19S), aunque la consulta usó WGS84. Hay que pedir
  `outSR=4326` para obtener longitud y latitud.
- El campo `Match_addr` tiene el mismo nombre que el de las patentes. Es probable que las
  patentes se geocodificaran con este mismo localizador, pero no lo podemos confirmar sin el SITMA.
- `Neighborhood` entrega el barrio directamente, lo que podría reemplazar la consulta a la
  capa de barrios para el caso de un punto.

**Sin verificar:** las propiedades `capabilities`, `maxLocations`, `maxBatchSize` y
`spatialReference`. La respuesta del servicio no las mostró completas.


Queremos usarlo en dos sentidos:

1. **Punto a dirección (reverse)**: cuando el usuario toca el mapa, obtener la dirección
   aproximada para mostrarla.
2. **Dirección a punto (forward)**: cuando el usuario busca una dirección, ubicarla en el mapa.

Además, para las patentes cuyo estado de geocodificación es `U` (UNTARGET), evaluamos si
conviene volver a geocodificar la dirección del negocio. Esto solo se hará con revisión
jurídica previa, porque `DIRECCION` es un dato del titular.

Preguntas para el SITMA:
- ¿Las patentes se geocodificaron con este mismo localizador? Eso permitiría comparar sus resultados.
- ¿Qué campos devuelve el localizador (score, tipo de dirección, dirección normalizada)?

## Qué no enviamos

- No enviamos RUT, razón social ni datos de representantes a ningún servicio externo.
- Las consultas al geocodificador van a la infraestructura municipal, no a terceros.
- No almacenamos el punto que el usuario toca. Solo se usa para la consulta.

## Respuestas del SITMA (2026-11-03)

- El servicio BETA se mantiene hasta marzo. Seguimos con esta versión y migramos cuando exista producción.
- No hay límite de consultas por minuto.
- `Status`: M = Match (la geocodificación hace match), T = Target (objetivo), U = Unmatch (sin match).

## Decisiones municipales

- Las patentes **bloqueadas** no se muestran en el mapa. Todas las demás (vigentes, Match,
  Target y Unmatch) sí se muestran.
