# Protocolo funcional Fase 1 - GARMIN-QPRO

## Objetivo

Definir el flujo funcional de la Fase 1 de GARMIN-QPRO para transformar actividades Garmin en un archivo TSV compatible con Quattro Pro.

La Fase 1 no implementa automatizaciones avanzadas ni edicion manual de resultados. El alcance queda limitado a:

- Entrada de archivos `FIT` individuales o paquetes `ZIP` con archivos `FIT`.
- Lectura estructurada de actividades.
- Normalizacion de campos.
- Clasificacion de actividad.
- Extraccion de metricas principales.
- Aplicacion de reglas especificas por tipo de actividad.
- Generacion de un TSV final para importacion en Quattro Pro.

## Flujo General

```text
FIT/ZIP
  -> deteccion de entrada
  -> extraccion de FIT si procede
  -> lectura de actividad
  -> normalizacion de datos
  -> clasificacion de actividad
  -> extraccion de metricas
  -> reglas especificas
  -> validaciones
  -> TSV Quattro Pro
```

## Entrada FIT/ZIP

### Archivos FIT

Cada archivo `FIT` representa una actividad Garmin. El sistema debe leer sus mensajes principales y extraer, como minimo:

- Fecha y hora de inicio.
- Tipo de deporte Garmin.
- Distancia.
- Duracion.
- Velocidad media.
- Velocidad maxima.
- Frecuencia cardiaca media.
- Frecuencia cardiaca maxima.
- Ascenso acumulado.
- Descenso acumulado.
- Calorias.

### Archivos ZIP

Un archivo `ZIP` puede contener uno o varios `FIT`. El sistema debe:

- Recorrer el contenido del paquete.
- Ignorar archivos que no sean `FIT`.
- Procesar cada `FIT` como actividad independiente.
- Mantener trazabilidad del nombre original del archivo.

Pendiente:

- Definir si se procesaran subcarpetas dentro del `ZIP`.
- Definir politica ante nombres duplicados dentro del `ZIP`.
- Definir si se conservaran archivos temporales extraidos.

## Lectura

La lectura debe transformar el contenido Garmin en una representacion interna estable, independiente de la libreria usada para leer `FIT`.

Campos internos minimos:

| Campo interno | Descripcion |
| --- | --- |
| `source_file` | Nombre del archivo de origen. |
| `start_time` | Fecha y hora de inicio de la actividad. |
| `garmin_sport` | Nombre o codigo de deporte indicado por Garmin. |
| `garmin_sub_sport` | Subtipo Garmin cuando exista. |
| `duration_seconds` | Duracion total en segundos. |
| `distance_meters` | Distancia total en metros. |
| `avg_speed_mps` | Velocidad media en metros por segundo. |
| `max_speed_mps` | Velocidad maxima en metros por segundo. |
| `avg_heart_rate` | Frecuencia cardiaca media en ppm. |
| `max_heart_rate` | Frecuencia cardiaca maxima en ppm. |
| `total_ascent_meters` | Ascenso acumulado en metros. |
| `total_descent_meters` | Descenso acumulado en metros. |
| `calories` | Calorias indicadas por Garmin. |

Pendiente:

- Confirmar si se usara tiempo total, tiempo en movimiento o tiempo transcurrido.
- Confirmar campos obligatorios exactos del TSV final de Quattro Pro.

## Normalizacion

La normalizacion convierte los valores Garmin a unidades y formatos consistentes antes de aplicar reglas.

### Unidades

| Magnitud | Entrada Garmin | Unidad interna | Salida TSV |
| --- | --- | --- | --- |
| Fecha | Timestamp Garmin | Fecha local | Pendiente |
| Hora | Timestamp Garmin | Hora local | Pendiente |
| Duracion | Segundos | Segundos | `HH:MM:SS` |
| Distancia | Metros | Metros | Kilometros con decimal |
| Velocidad | m/s | km/h | Numero decimal |
| Frecuencia cardiaca | ppm | ppm | Entero |
| Ascenso/descenso | Metros | Metros | Entero |
| Calorias | kcal | kcal | Entero |

### Reglas de formato

- Los numeros decimales deben exportarse con separador decimal compatible con Quattro Pro.
- Las fechas deben exportarse en un formato estable y no ambiguo.
- Los campos vacios deben representarse de forma uniforme.

Pendiente:

- Confirmar si Quattro Pro espera coma o punto como separador decimal.
- Confirmar si la fecha debe ir en formato `DD/MM/YYYY`, `YYYY-MM-DD` u otro.
- Confirmar si los campos vacios deben ir como celda vacia, `0` o texto especifico.

## Clasificacion de Actividad

La clasificacion traduce el deporte Garmin a un codigo o nombre esperado por la hoja Quattro Pro.

### Mapeo de nombres Garmin a codigos Quattro Pro

| Garmin sport | Garmin sub sport | Codigo Quattro Pro | Estado |
| --- | --- | --- | --- |
| `running` | cualquiera | Pendiente | Pendiente de documentar |
| `cycling` | cualquiera | Pendiente | Pendiente de documentar |
| `walking` | cualquiera | Pendiente | Pendiente de documentar |
| `hiking` | cualquiera | Pendiente | Pendiente de documentar |
| `swimming` | `lap_swimming` | Pendiente | Pendiente de documentar |
| `swimming` | `open_water` | Pendiente | Pendiente de documentar |
| `training` | cualquiera | Pendiente | Pendiente de documentar |
| `fitness_equipment` | cualquiera | Pendiente | Pendiente de documentar |
| otro | cualquiera | Pendiente | Revisar manualmente |

Pendiente:

- Completar codigos reales usados por Quattro Pro.
- Confirmar si el mapeo depende solo de `sport` o tambien de `sub_sport`.
- Confirmar codigo por defecto para actividades no reconocidas.

## Extraccion de Metricas

Metricas minimas para la Fase 1:

| Metrica | Origen preferente | Regla |
| --- | --- | --- |
| Fecha | Inicio de actividad | Convertir a fecha local. |
| Hora | Inicio de actividad | Convertir a hora local. |
| Tipo | Clasificacion interna | Convertir a codigo Quattro Pro. |
| Duracion | Total activity time | Formatear como `HH:MM:SS`. |
| Distancia | Total distance | Convertir de metros a kilometros. |
| VMED | Velocidad media o calculada | Ver formula VMED. |
| VMAX | Velocidad maxima Garmin | Ver formula VMAX. |
| FC media | Average heart rate | Entero si existe. |
| FC maxima | Max heart rate | Entero si existe. |
| Ascenso | Total ascent | Entero en metros. |
| Descenso | Total descent | Entero en metros. |
| Calorias | Calories | Entero si existe. |

Pendiente:

- Definir si se incluiran cadencia, potencia, ritmo, temperatura u otros campos.
- Confirmar orden exacto de columnas del TSV.
- Confirmar nombres exactos de columnas si el TSV debe incluir cabecera.

## Formatos de Campos TSV

Propuesta inicial de campos:

| Columna | Campo | Formato propuesto | Obligatorio |
| --- | --- | --- | --- |
| 1 | Fecha | `DD/MM/YYYY` | Si |
| 2 | Hora | `HH:MM:SS` | Pendiente |
| 3 | Actividad | Codigo Quattro Pro | Si |
| 4 | Duracion | `HH:MM:SS` | Si |
| 5 | Distancia | Kilometros con 2 decimales | Si para actividades con distancia |
| 6 | VMED | km/h con 2 decimales | Si cuando haya distancia y duracion |
| 7 | VMAX | km/h con 2 decimales | No |
| 8 | FC media | Entero | No |
| 9 | FC maxima | Entero | No |
| 10 | Ascenso | Entero en metros | No |
| 11 | Descenso | Entero en metros | No |
| 12 | Calorias | Entero | No |
| 13 | Archivo origen | Texto | No |

Reglas TSV:

- Separador de columnas: tabulador.
- Separador de filas: salto de linea.
- Sin comillas salvo que Quattro Pro lo requiera.
- Sin separadores de miles.

Pendiente:

- Confirmar si el archivo TSV debe incluir fila de cabecera.
- Confirmar codificacion requerida: `UTF-8`, `ANSI` u otra.
- Confirmar separador decimal esperado.
- Confirmar columnas definitivas y su orden exacto.

## Formulas VMED/VMAX

### VMED

Velocidad media expresada en km/h.

Formula preferente cuando Garmin proporcione velocidad media valida:

```text
VMED = avg_speed_mps * 3.6
```

Formula alternativa cuando no exista velocidad media pero si distancia y duracion:

```text
VMED = (distance_meters / duration_seconds) * 3.6
```

Validaciones:

- Si `duration_seconds` es `0` o esta vacio, VMED queda vacia.
- Si `distance_meters` es `0` o esta vacio, VMED queda vacia salvo regla especifica por actividad.
- Redondeo propuesto: 2 decimales.

Pendiente:

- Confirmar si VMED debe calcularse con duracion total o tiempo en movimiento.
- Confirmar si ciertas actividades deben usar ritmo en lugar de velocidad.

### VMAX

Velocidad maxima expresada en km/h.

Formula:

```text
VMAX = max_speed_mps * 3.6
```

Validaciones:

- Si Garmin no informa velocidad maxima, VMAX queda vacia.
- Si VMAX es menor que VMED, marcar advertencia para revision.
- Redondeo propuesto: 2 decimales.

Pendiente:

- Definir umbrales para descartar picos irreales.
- Confirmar si natacion, gimnasio u otras actividades deben dejar VMAX vacia.

## Reglas Especiales por Tipo de Actividad

### Carrera

- Usar distancia, duracion, VMED y VMAX si existen.
- Mantener frecuencia cardiaca y calorias si Garmin las informa.

Pendiente:

- Confirmar codigo Quattro Pro.
- Confirmar si Quattro Pro espera ritmo min/km ademas de VMED.

### Ciclismo

- Usar distancia, duracion, VMED y VMAX si existen.
- Mantener ascenso y descenso como metricas relevantes.

Pendiente:

- Confirmar codigo Quattro Pro.
- Definir tratamiento de potencia y cadencia si aparecen.

### Caminata

- Usar distancia y duracion.
- Calcular VMED si no viene informada.
- VMAX opcional.

Pendiente:

- Confirmar codigo Quattro Pro.
- Confirmar si caminata y senderismo son codigos distintos.

### Senderismo

- Usar distancia, duracion, ascenso y descenso.
- Calcular VMED si no viene informada.

Pendiente:

- Confirmar codigo Quattro Pro.
- Definir si ascenso es obligatorio.

### Natacion

- Usar distancia y duracion si existen.
- VMED puede calcularse en km/h, aunque podria no ser el formato mas util.
- VMAX queda pendiente de decision.

Pendiente:

- Confirmar codigo Quattro Pro para piscina y aguas abiertas.
- Confirmar si se deben exportar largos, brazadas o ritmo por 100 m.

### Entrenamiento / Gimnasio

- Duracion, frecuencia cardiaca y calorias son las metricas principales.
- Distancia, VMED y VMAX normalmente quedan vacias salvo que Garmin informe datos validos.

Pendiente:

- Confirmar codigos Quattro Pro por subtipo.
- Definir tratamiento de actividades sin distancia.

### Actividad Desconocida

- Exportar campos disponibles.
- Marcar actividad como pendiente de revision.
- No inventar codigos Quattro Pro.

Pendiente:

- Confirmar codigo o texto de revision manual.

## Validaciones

Validaciones minimas antes de generar TSV:

- El archivo de entrada existe y es legible.
- Si la entrada es `ZIP`, contiene al menos un `FIT`.
- Cada `FIT` puede leerse sin error critico.
- La actividad tiene fecha de inicio.
- La actividad tiene tipo Garmin o queda marcada como desconocida.
- La duracion no es negativa.
- La distancia no es negativa.
- VMED y VMAX no son negativas.
- VMAX no deberia ser menor que VMED cuando ambas existan.
- Los campos obligatorios del TSV no deben quedar vacios.

Validaciones de consistencia:

- Si hay distancia positiva y duracion positiva, VMED debe existir.
- Si no hay distancia, VMED debe quedar vacia salvo regla especifica.
- Si no hay frecuencia cardiaca, los campos de FC quedan vacios.
- Si hay valores extremos, deben marcarse para revision.

Pendiente:

- Definir umbrales de valores extremos por actividad.
- Definir si una validacion fallida bloquea la exportacion o solo genera aviso.
- Definir formato del informe de validaciones.

## Casos de Error

| Caso | Resultado esperado |
| --- | --- |
| Archivo inexistente | Error bloqueante. No se genera TSV. |
| Extension no soportada | Error bloqueante. Solo se aceptan `FIT` y `ZIP`. |
| ZIP vacio | Error bloqueante. |
| ZIP sin archivos FIT | Error bloqueante. |
| FIT corrupto o ilegible | Registrar error y continuar con otros FIT si existen. |
| Actividad sin fecha | Error de actividad. No exportar esa fila. |
| Actividad sin tipo Garmin | Exportar como desconocida si el resto de campos minimos existen. |
| Duracion cero | Dejar VMED vacia y registrar advertencia. |
| Distancia cero | Dejar VMED vacia salvo regla especifica. |
| Codigo Quattro Pro desconocido | Marcar como pendiente de revision. |

Pendiente:

- Definir si un error parcial debe devolver codigo global de fallo.
- Definir nombre y ubicacion del log de errores.
- Definir si el TSV debe generarse aunque existan advertencias.

## Salida TSV para Quattro Pro

La salida de Fase 1 sera un archivo `.tsv` con una fila por actividad procesada.

Requisitos iniciales:

- Una actividad por linea.
- Campos separados por tabulador.
- Valores ya normalizados.
- Codigos de actividad compatibles con Quattro Pro cuando esten documentados.
- Actividades no mapeadas marcadas para revision.

Pendiente:

- Confirmar nombre por defecto del archivo de salida.
- Confirmar ruta por defecto de salida.
- Confirmar si se debe generar un TSV unico por lote o uno por archivo.
- Confirmar si debe generarse tambien un informe de errores/advertencias.

## Pendientes Globales

- Obtener tabla definitiva de codigos Quattro Pro.
- Confirmar formato exacto de columnas esperado por Quattro Pro.
- Confirmar reglas de separador decimal y codificacion.
- Confirmar origen exacto de duracion para VMED.
- Documentar reglas completas por actividad Garmin.
- Definir politica de errores bloqueantes y advertencias.
