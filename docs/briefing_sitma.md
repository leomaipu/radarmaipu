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

Queremos usarlo en dos sentidos:

1. **Punto a dirección (reverse)**: cuando el usuario toca el mapa, obtener la dirección
   aproximada para mostrarla.
2. **Dirección a punto (forward)**: cuando el usuario busca una dirección, ubicarla en el mapa.

Además, para las patentes cuyo estado de geocodificación es `U` (UNTARGET), evaluamos si
conviene volver a geocodificar la dirección del negocio. Esto solo se hará con revisión
jurídica previa, porque `DIRECCION` es un dato del titular.

Preguntas para el SITMA:
- ¿Este servicio es de producción o de prueba? Lo llamamos BETA y no queremos depender de él si cambia sin aviso.
- ¿Podemos tener un endpoint estable de producción?
- ¿Cuál es el límite de consultas por minuto?
- ¿Confirman el significado de `Status`: M = Match, T = Target, U = UNTARGET?
- ¿Qué campos devuelve el localizador (score, tipo de dirección, dirección normalizada)?

## Qué no enviamos

- No enviamos RUT, razón social ni datos de representantes a ningún servicio externo.
- Las consultas al geocodificador van a la infraestructura municipal, no a terceros.
- No almacenamos el punto que el usuario toca. Solo se usa para la consulta.

## Pendiente de decisión municipal

- Si las patentes **bloqueadas** se muestran u ocultan en el mapa. Mientras no se decida,
  se muestran con su estado.
