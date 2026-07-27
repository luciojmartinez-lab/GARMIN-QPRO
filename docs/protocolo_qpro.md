# Protocolo funcional y técnico — GARMIN‑QPRO

**Versión:** 0.5 integrada  
**Ámbito:** Fase 1 — FIT/ZIP → línea TSV lista para Quattro Pro  
**Estado:** especificación principal de implementación

Este documento consolida:

1. las instrucciones operativas del GPT Garmin → Quattro Pro;
2. el protocolo Garmin → Quattro Pro v5;
3. la estructura visual real de la hoja Quattro Pro;
4. las reglas validadas durante el procesamiento de actividades reales.

Cuando exista conflicto, prevalece este orden:

1. indicación explícita del usuario para la actividad concreta;
2. regla especial exacta por nombre Garmin;
3. mapeo y reglas de este protocolo;
4. tabla de referencia de Quattro Pro;
5. consulta al usuario.

---

# 1. Objetivo

Convertir actividades Garmin (`.FIT` o `.ZIP` con archivos `.FIT`) en líneas TSV que puedan copiarse y pegarse directamente en la hoja de entrenamiento de Quattro Pro.

La salida debe conservar exactamente:

- orden de columnas;
- código de la primera columna;
- fila utilizada en las fórmulas;
- tabuladores;
- fórmulas de Quattro Pro;
- apóstrofos iniciales;
- ceros iniciales;
- coma decimal;
- celdas vacías;
- unidades y redondeos establecidos.

La prioridad absoluta es que la línea quede con el mismo formato que las filas existentes de Quattro Pro.

---

# 2. Principios generales

1. Leer siempre el FIT original.
2. No trabajar desde Excel, CSV, TCX ni resúmenes previos salvo petición expresa.
3. Si se recibe un ZIP, localizar automáticamente los FIT que contiene.
4. No inventar datos.
5. No usar valores neutros (`'000`, `0,0` o vacío) sin haber agotado antes las fuentes posibles.
6. Buscar la información en todas las estructuras FIT relevantes.
7. Priorizar la fuente más próxima a lo mostrado por Garmin Connect.
8. Detectar el nombre real de la actividad Garmin.
9. No usar encabezados amarillos de bloque como código.
10. No asignar `ENT` como código provisional.
11. Si el usuario indica explícitamente código o fila, su indicación manda.
12. Validar todos los campos antes de generar la línea.
13. Nunca mezclar varias actividades en una sola línea.
14. No considerar soportado un tipo de actividad hasta disponer de al menos un FIT y una salida TSV validada.

---

# 3. Flujo general

```text
FIT o ZIP
  → validación de entrada
  → extracción segura de FIT
  → lectura de mensajes FIT y developer fields
  → detección del nombre Garmin
  → normalización a un modelo interno
  → clasificación a código Quattro Pro
  → selección de la fila
  → selección de la fuente de cada campo
  → aplicación de reglas especiales
  → validaciones de coherencia
  → formateo exacto
  → línea TSV
  → observaciones, solo cuando procedan
```

---

# 4. Fuentes de datos FIT

Deben revisarse, cuando existan:

- `session`;
- `activity`;
- `sport`;
- `workout`;
- `lap`;
- `record`;
- `event`;
- `developer data`;
- running dynamics;
- power;
- training load;
- campos propietarios de Garmin;
- estructuras de fuerza;
- intervalos, únicamente cuando este protocolo lo permita.

La procedencia de cada valor debe quedar registrada internamente.

---

# 5. Entrada FIT y ZIP

## 5.1 FIT individual

Cada FIT representa una actividad independiente.

Conservar:

- nombre del archivo;
- tamaño;
- hash;
- fecha/hora Garmin;
- nombre Garmin;
- estado de lectura.

## 5.2 ZIP

Un ZIP puede contener uno o varios FIT.

Reglas:

- recorrer subcarpetas;
- ignorar archivos que no sean FIT;
- impedir rutas inseguras;
- procesar cada FIT de forma independiente;
- continuar con los demás si uno falla;
- eliminar temporales al terminar;
- conservar la ruta interna del FIT.

## 5.3 Varias actividades

Si el archivo o lote contiene varias actividades:

1. enumerarlas;
2. si el usuario pidió procesamiento por lotes, procesarlas todas;
3. si no lo pidió y existe una actividad claramente principal, procesar esa;
4. si no existe una actividad claramente principal, preguntar cuál debe convertirse.

Nunca fusionar varias actividades en una línea TSV.

---

# 6. Identificación de actividad

## 6.1 Nombre Garmin

Buscar el nombre real de la actividad Garmin.

Si no aparece:

- no asignar automáticamente `ENT`;
- mostrar los candidatos disponibles;
- solicitar aclaración si el código no puede determinarse con seguridad.

## 6.2 Mapeo validado

| Nombre Garmin | Código |
|---|---:|
| `EB0 - Cal. Estadio` | `CAL` |
| `EB0 - Cal. Pesas - 1` | `CLP` |
| `EB0 - Cal. Pesas - 2` | `FPN` |
| `EB1 - Carrera - 1` | `ENT` |
| `EB1 - Carrera - 2` | `ENT` |
| `EB5 - MOVILIDAD VALLAS` | `MOF` |
| `EB5 - Pesas - Fase` | `PES` |
| `EB0 - Vuelta a la calma` | `FIN` |
| `EB1 - Carrera Tec Altura` | `ENT` |
| `EB1 - Carrera Técnica-Triple` | `ENT` |
| `EB1 - Carrera Tec Triple` | `ENT` |

Regla contextual:

> Si Garmin muestra simplemente `Carrera` y el usuario indica que se trata de un calentamiento de competición o de una carrera simple previa, usar `CAL`.

## 6.3 Códigos válidos conocidos

```text
CAL, CLP, ENT, CAR, SER, REC, TEC, TEF, MUL, CMP, CMF, EST,
FIN, FPN, AQG, PLY, TST, CAM, FLK, BIC, PES, BMD,
MOV, MOF, ESC, ESF, CIR
```

---

# 7. Claves, familias de fila y resolución dinámica

La lógica funcional debe depender de la **clave de la primera columna (A)**, no de un número de fila fijo.

Los números de fila pueden cambiar si se insertan, eliminan o desplazan filas en Quattro Pro. Por tanto:

1. la clave determina el conjunto de reglas;
2. el número de fila se obtiene en tiempo de ejecución o desde una configuración actualizable;
3. las fórmulas se generan sustituyendo la fila resuelta;
4. nunca se debe deducir la naturaleza de una actividad únicamente por su posición actual.

## 7.1 Familias de claves

### A. Calentamiento, carrera, entrenamiento y desplazamiento

```text
CAL, CLP, ENT, CAR, SER, REC, TEC, FIN, FPN, AQG,
PLY, CMP, CAM, FLK, BIC, MOV, ESC
```

Estas claves usan los datos reales disponibles de velocidad, ritmo, distancia,
cadencia, potencia y dinámica, conforme a las reglas específicas de cada actividad.

### B. Fuerza, competición, técnica de fuerza y estiramientos

```text
TEF, MUL, CMF, EST, TST, PES, BMD, MOF, CIR, ESF
```

Estas claves aplican la plantilla de fuerza definida en la sección 18.

## 7.2 Mapa visual actual, solo orientativo

La hoja mostrada actualmente sitúa, entre otras, estas claves en las filas indicadas:

| Clave | Fila actual observada |
|---|---:|
| CAL | 18 |
| CLP | 20 |
| ENT | 23 |
| CAR | 25 |
| SER | 27 |
| REC | 29 |
| TEC | 31 |
| TEF | 32 |
| MUL | 34 |
| CMF | 36 |
| CMP | 51 |
| EST | 38 |
| FIN | 41 |
| FPN | 44 |
| AQG | 47 |
| PLY | 49 |
| TST | 53 |
| CAM | 55 |
| FLK | 57 |
| BIC | 59 |
| PES | 61 |
| BMD | 63 |
| MOV | 65 |
| MOF | 66 |
| ESF | 69 en la imagen más reciente |
| CIR | 71 en la imagen más reciente |
| ESC | 68 en la imagen más reciente |

Este mapa **no es una regla permanente**. Solo sirve como referencia de la
disposición actual.

## 7.3 Prioridad para obtener la fila

1. Fila indicada expresamente por el usuario.
2. Fila localizada por la clave en una tabla/configuración actualizada.
3. Fila detectada directamente en la hoja, si en el futuro existe lectura de Quattro Pro.
4. Preguntar al usuario si no puede resolverse con seguridad.

No usar la fila 20 como valor provisional en una salida final.

## 7.4 Separación definitiva CMP / CMF

La antigua duplicidad de `CMP` queda eliminada.

- `CMP`: competición de velocidad/calentamiento. Pertenece a la familia de
  calentamiento, carrera y entrenamiento.
- `CMF`: competición de fuerza. Pertenece a la familia de fuerza, competición
  de fuerza y actividades asimiladas.

En la disposición actual observada:

```text
CMF → fila 36
CMP → fila 51
```

Estas filas siguen siendo orientativas; la regla funcional depende de la clave.

# 8. Orden exacto de columnas TSV

La salida contiene 25 columnas:

| Nº | Campo |
|---:|---|
| 1 | CÓDIGO |
| 2 | RMED |
| 3 | VMED |
| 4 | VMED M/S |
| 5 | RMAX |
| 6 | VMAX |
| 7 | VMAX M/S |
| 8 | DISTANCIA |
| 9 | PPME |
| 10 | PPMAX |
| 11 | MIN |
| 12 | RITMO |
| 13 | AER |
| 14 | ANA |
| 15 | CADM |
| 16 | CADX |
| 17 | ZAN |
| 18 | TCS |
| 19 | CARGA |
| 20 | PTM |
| 21 | PTX |
| 22 | RVM |
| 23 | OVM |
| 24 | CARGA_AGUDA |
| 25 | CARGA_CRONICA |

Las columnas `CARGA_AGUDA` y `CARGA_CRONICA` deben ir siempre al final. Si no existen en el FIT, quedan vacías.

No incluir cabecera en la línea lista para pegar.

---

# 9. Formato TSV

- Una fila de 25 columnas contiene exactamente 24 tabuladores. No se añade ningún separador después de la columna 25. Si la columna 25 está vacía, la línea termina necesariamente con el tabulador estructural que separa las columnas 24 y 25.
- Separador de filas: salto de línea.
- Coma decimal.
- Sin tabla Markdown.
- Sin comillas envolventes.
- Sin separadores de miles.
- Celdas no disponibles: vacías, salvo que exista una regla explícita.
- Codificación de archivo: UTF‑8.
- La respuesta principal debe incluir la línea dentro de un bloque de texto plano.

---

# 10. Campos de texto

Deben generarse con apóstrofo inicial:

```text
PPME
PPMAX
MIN
RITMO
CADM
CADX
TCS
CARGA
PTM
PTX
RVM
OVM
CARGA_AGUDA
CARGA_CRONICA
```

Formatos:

| Campo | Formato | Ejemplo |
|---|---|---|
| PPME / PPMAX | `'###` | `'098` |
| MIN | `'###` | `'044` |
| RITMO | `'MM,SS` | `'07,15` |
| CADM / CADX | `'###` | `'151` |
| TCS | `'###` | `'305` |
| CARGA | `'###` | `'133` |
| PTM / PTX | `'###` | `'208` |
| RVM | apóstrofo + decimal | `'10,1` |
| OVM | apóstrofo + decimal | `'08,8` |
| CARGA_AGUDA / CRONICA | `'###` | `'123` |

No convertir automáticamente un campo ausente en `'000`.

---

# 11. RMED, VMED, RMAX, VMAX y fórmulas

## 11.1 Significado

`RMED` y `VMED` son entradas alternativas para obtener `VMED M/S`.

`RMAX` y `VMAX` son entradas alternativas para obtener `VMAX M/S`.

- Si existe velocidad en km/h, se usa `VMED` o `VMAX`.
- Si no existe velocidad y se dispone de ritmo, se usa `RMED` o `RMAX`.
- No rellenar simultáneamente ambos campos de una pareja sin una regla validada.

## 11.2 Fórmula robusta de VMED M/S

Para una fila resuelta dinámicamente como `n`:

```text
@SI(@ESERR(@SI(Cn<>"";(Cn*1000)/3600;1000/(Bn*60)));0;@SI(Cn<>"";(Cn*1000)/3600;1000/(Bn*60)))
```

Ejemplo actual en la fila 23:

```text
@SI(@ESERR(@SI(C23<>"";(C23*1000)/3600;1000/(B23*60)));0;@SI(C23<>"";(C23*1000)/3600;1000/(B23*60)))
```

La fórmula debe construirse desde la clave y la fila actual resuelta, no
almacenarse con `23` de forma permanente.

## 11.3 Fórmula robusta confirmada de VMAX M/S

Para una fila resuelta dinámicamente como `n`:

```text
@SI(@ESERR(@SI(Fn<>"";(Fn*1000)/3600;1000/(En*60)));0;@SI(Fn<>"";(Fn*1000)/3600;1000/(En*60)))
```

Ejemplo actual en la fila 23:

```text
@SI(@ESERR(@SI(F23<>"";(F23*1000)/3600;1000/(E23*60)));0;@SI(F23<>"";(F23*1000)/3600;1000/(E23*60)))
```

Esta fórmula queda confirmada como definitiva.

## 11.4 Uso en ambas familias

Las fórmulas de las columnas `VMED M/S` y `VMAX M/S` deben estar presentes
tanto en filas de carrera como en filas de fuerza.

La diferencia entre las familias no es la existencia de la fórmula, sino los
valores de entrada:

- en carrera/calientamiento se rellenan VMED, VMAX, RMED o RMAX cuando existen;
- en fuerza se dejan vacíos VMED y VMAX, y las fórmulas robustas devuelven
  `0,00` sin error.

# 12. Tiempo en movimiento

Para actividades de carrera y cinta, los campos:

```text
MIN
VMED
RITMO
```

deben basarse en tiempo en movimiento.

Prioridad:

1. `total_moving_time` válido;
2. si falta, es cero o inválido, derivar tiempo en movimiento desde `record`;
3. contar segundos con `enhanced_speed` o `speed` superior a `0,3 m/s`.

No usar automáticamente tiempo transcurrido o duración total cuando el protocolo exige tiempo en movimiento.

---

# 13. Cadencia

Garmin Connect presenta cadencia de carrera en pasos por minuto (`spm`).

## 13.1 Conversión

Si el FIT contiene cadencia en rango típico de ciclos/minuto (`≤120`) y existe `fractional_cadence`:

```text
cadencia_spm = (cadence + fractional_cadence) * 2
```

Si el FIT ya contiene valores en rango típico de pasos/minuto (`≈130–200`), no multiplicar por dos.

## 13.2 Salida

- `CADM`: cadencia media real, redondeada.
- `CADX`: cadencia máxima real.
- Ambos como texto `'###`.
- No duplicar automáticamente `CADM`.
- Solo aplicar la conversión ×2 a `CADX` cuando el FIT guarde ciclos/minuto y la hoja espere pasos/minuto.

---

# 14. Carga de ejercicio

La columna 19, `CARGA`, debe contener exclusivamente:

```text
Carga de ejercicio / Exercise Load
```

Prioridad:

1. Exercise Load de `session`;
2. Exercise Load en `developer data`;
3. Training Load equivalente claramente identificado.

Si es decimal, redondear.

Salida:

```text
'###
```

## 14.1 Prohibiciones

No usar como `CARGA`:

- pérdida de líquido estimada;
- líquido neto;
- calorías activas;
- calorías en reposo;
- calorías totales;
- hidratación;
- nutrición;
- campos `unknown_*` sin identificación inequívoca;
- candidatos internos que no coincidan con la carga visible en Garmin Connect.

## 14.2 Caso validado de fuerza

```text
AER = 2,7
ANA = 3,2
CARGA = '133
```

En ese caso no usar `'1261` ni `'148`.

---

# 15. Training Effect

## 15.1 AER

Training Effect aeróbico.

Fuentes:

- `total_training_effect`;
- equivalente en developer data;
- campo propietario inequívoco.

## 15.2 ANA

Training Effect anaeróbico.

Fuentes:

- `total_anaerobic_training_effect`;
- equivalente en developer data;
- campo propietario inequívoco.

No forzar `ANA` a `0,0` si el FIT contiene un valor real, especialmente en actividades de fuerza.

---

# 16. Carga aguda y carga crónica

Buscar:

- Acute Load;
- Acute Training Load;
- Chronic Load;
- Chronic Training Load;
- Load Ratio;
- Training Status;
- equivalentes propietarios.

Prioridad:

1. `session`;
2. developer data;
3. campos propietarios Garmin;
4. equivalentes claros relacionados con Training Load.

Reglas:

- nunca calcular manualmente;
- nunca estimar;
- nunca inferir desde Exercise Load;
- si no existen, dejar vacíos;
- elegir la fuente más cercana al resumen de Garmin Connect.

Formato:

```text
'###
```

---

# 17. Regla especial CAL

## 17.1 Identificación exacta

La regla solo se aplica cuando el nombre contiene exactamente:

```text
EB0 - Cal. Estadio
```

Código:

```text
CAL
```

Fila:

```text
18
```

## 17.2 Intervalo de calentamiento

Únicamente en esta actividad se analizan intervalos/laps filtrados por:

```text
Tipo de paso = Calentamiento
```

Los siguientes campos deben obtenerse de ese resumen de intervalo:

```text
CADM
CADX
ZAN
TCS
PTM
PTX
RVM
OVM
```

No usar para ellos el promedio global.

## 17.3 Prohibición fuera de CAL

En cualquier otra actividad:

- no usar intervalos para sustituir medias globales;
- no aplicar el filtro “Calentamiento”;
- no transportar esta regla por similitud de nombre.

## 17.4 Ausencia del intervalo

Si no aparece el intervalo exacto:

- no sustituirlo silenciosamente por el resumen global;
- mostrar advertencia;
- dejar vacíos los campos afectados o solicitar revisión.

---

# 18. Plantilla exacta de fuerza, competición y asimiladas

Esta plantilla se aplica a las claves:

```text
TEF, MUL, CMF, EST, TST, PES, BMD, MOF, CIR, ESF
```

La identificación se realiza por la clave de la columna A, no por el número de
fila.

## 18.1 Valores obligatorios de la plantilla

| Campo | Valor de salida |
|---|---|
| RMED | vacío |
| VMED | vacío |
| VMED M/S | fórmula robusta de la fila; resultado esperado `0,00` |
| RMAX | vacío |
| VMAX | vacío |
| VMAX M/S | fórmula robusta de la fila; resultado esperado `0,00` |
| DISTANCIA | `0,00` |
| RITMO | `'00,00` |
| CADM | `'000` |
| CADX | `'000` |
| ZAN | `0,00` |
| TCS | `'000` |
| CARGA | `'000` cuando no existe Exercise Load real |
| PTM | `'000` |
| PTX | `'000` |
| RVM | `'000` |
| OVM | `'000` |

El formato es obligatorio. No son equivalentes:

- vacío;
- `0`;
- `0,0`;
- `0,00`;
- `'000`;
- `'00,00`.

Cada campo debe conservar exactamente el valor indicado.

## 18.2 Campos que sí pueden contener datos reales

Aunque se aplique la plantilla de fuerza, deben extraerse los datos reales
cuando existan para:

```text
PPME
PPMAX
MIN
AER
ANA
CARGA
CARGA_AGUDA
CARGA_CRONICA
```

En particular, `CARGA` debe contener Exercise Load real cuando exista. Solo se
usa `'000` cuando se ha buscado exhaustivamente y el dato no está disponible.

## 18.3 Carga levantada frente a Exercise Load

La carga levantada en series de pesas no es la columna `CARGA` de esta hoja.

La columna `CARGA` sigue representando:

```text
Carga de ejercicio / Exercise Load
```

No confundirla con peso levantado, calorías, líquido neto o hidratación.

# 19. FIT recortados

Cuando un FIT esté recortado:

- detectar inicio o final incompletos;
- no reconstruir silenciosamente valores;
- extraer únicamente datos presentes;
- informar qué métricas pueden estar incompletas;
- permitir una salida parcial solo si el usuario lo acepta o si los campos esenciales siguen siendo fiables.

---

# 20. Validación obligatoria

Antes de generar la línea comprobar:

- archivo leído;
- nombre Garmin;
- código;
- fila;
- distancia;
- tiempo activo o en movimiento;
- velocidad media;
- velocidad máxima;
- ritmo;
- pulso medio;
- pulso máximo;
- cadencia media;
- cadencia máxima;
- potencia media;
- potencia máxima;
- Exercise Load;
- Training Effect aeróbico;
- Training Effect anaeróbico;
- dinámica de carrera;
- carga aguda;
- carga crónica.

---

# 21. Reglas de coherencia

Comprobar:

- `VMAX ≥ VMED`;
- ritmo compatible con VMED;
- distancia compatible con tiempo;
- cadencia expresada en spm;
- `PPME ≤ PPMAX`;
- `PTM ≤ PTX`;
- `CADM ≤ CADX`;
- CARGA distinta de calorías e hidratación;
- ANA no forzada a cero;
- regla CAL aplicada únicamente a CAL;
- cargas aguda y crónica no calculadas;
- número exacto de columnas;
- apóstrofos y ceros iniciales;
- fórmula referida a la fila actual de la clave;
- familia determinada por la clave de la columna A;
- valores neutros de fuerza exactamente formateados;
- fórmula referida a la fila correcta.

Si hay discrepancia:

1. revisar el FIT de nuevo;
2. buscar en otras fuentes originales;
3. corregir si existe evidencia;
4. informar solo si no puede resolverse.

---

# 22. Formato habitual de respuesta

```text
Actividad detectada:
Nombre Garmin:
Código usado:
Fila usada para fórmulas:
Regla especial aplicada:

Línea TSV:
<línea con tabuladores>

Observaciones:
<solo si existen ausencias, discrepancias o decisiones relevantes>
```

La línea TSV es siempre la salida principal.

Si el usuario pide además Excel, se puede generar `.xlsx`, pero no sustituye a la línea TSV.

---

# 23. Ejemplo validado CAL

```text
CAL		2,32	@SI(C18<>"";(C18*1000)/3600;1000/(B18*60))		10,45	@SI(F18<>"";(F18*1000)/3600;1000/(E18*60))	1,71	'098	'118	'044	'25,52	1,1	0,0	'034	'167	0,73	'322	'055	'037	'295	'10,9	'07,2		
```

Las dos últimas columnas están vacías porque no constan CARGA_AGUDA ni CARGA_CRONICA.

---

# 24. Modelo interno recomendado

```text
source_zip
source_file
source_path
file_hash

activity_name
sport
sub_sport
start_time_utc
start_time_local

total_elapsed_time
total_timer_time
total_moving_time
derived_moving_time
total_distance
avg_speed
max_speed
avg_heart_rate
max_heart_rate
exercise_load
acute_load
chronic_load
aerobic_training_effect
anaerobic_training_effect

avg_cadence
max_cadence
avg_power
max_power
avg_ground_contact_time
avg_vertical_oscillation
avg_vertical_ratio
avg_stride_length

laps[]
records[]
events[]
strength_sets[]
developer_fields[]
field_sources{}
warnings[]
```

Cada valor debe conservar:

- dato;
- unidad;
- fuente;
- transformación aplicada;
- confianza.

---

# 25. Arquitectura recomendada

```text
src/garmin_qpro/
├── input/
│   ├── fit_loader.py
│   └── zip_loader.py
├── fit/
│   ├── parser.py
│   ├── models.py
│   └── field_registry.py
├── classify/
│   ├── activity_name.py
│   └── mappings.py
├── rules/
│   ├── base.py
│   ├── cal.py
│   ├── running.py
│   ├── strength.py
│   ├── competition.py
│   └── registry.py
├── qpro/
│   ├── schema.py
│   ├── rows.py
│   ├── formatter.py
│   ├── formulas.py
│   └── tsv.py
├── validation/
│   ├── checks.py
│   └── report.py
└── cli.py
```

---

# 26. Pruebas obligatorias

## 26.1 Unitarias

- mapeo de nombres;
- selección de filas;
- fórmulas estándar por fila;
- fórmulas `@ESERR`;
- normalización de coma decimal;
- apóstrofos;
- tiempo en movimiento;
- cadencia rpm → spm;
- selección de Exercise Load;
- descarte de calorías/hidratación;
- AER y ANA;
- filtro CAL exacto;
- rechazo del filtro CAL en otras actividades;
- ZIP seguro;
- 25 columnas exactas.

## 26.2 Regresión

Cada caso validado debe incluir:

```text
FIT de entrada
TSV esperado exacto
```

Comparación carácter por carácter:

- tabuladores;
- fórmulas;
- apóstrofos;
- ceros;
- comas;
- vacíos;
- número de columnas.

---

# 27. Pendientes bloqueantes

1. Obtener ejemplos FIT + TSV validados para `CMP` y `CMF`.
2. Confirmar reglas específicas adicionales que diferencien competición de velocidad y competición de fuerza.
3. Obtener ejemplos FIT + TSV de:
   - CAL;
   - CLP;
   - FPN;
   - ENT;
   - PES;
   - MOF;
   - CMP.
4. Confirmar si las columnas CARGA_AGUDA y CARGA_CRONICA ya existen físicamente en la hoja actual o se añaden durante la migración.
5. Documentar reglas de cada código restante.
6. Confirmar el formato exacto de RMED y RMAX cuando se utilizan.
7. Confirmar la fuente y redondeo exactos de ZAN.
8. Confirmar cómo se obtiene VMAX cuando Garmin Connect y el FIT difieren.
9. Definir política de salidas parciales para FIT recortados.

---

# 28. Próximo paso de implementación

1. Incorporar este documento al repositorio.
2. Crear `qpro/schema.py` con las 25 columnas.
3. Crear `qpro/rows.py` con códigos y filas.
4. Crear `qpro/formulas.py` con fórmulas estándar.
5. No implementar aún las fórmulas `@ESERR` hasta obtenerlas literalmente.
6. Crear el modelo interno.
7. Implementar carga segura de FIT/ZIP.
8. Implementar detección del nombre Garmin.
9. Implementar primero el caso CAL.
10. Validarlo con un FIT real y el TSV esperado.

# 29. Cambios de la versión 0.4

- Se elimina la dependencia funcional de números de fila fijos.
- La clave de la columna A pasa a determinar la familia de reglas.
- Se incorpora `ESC`.
- Se separan las familias carrera/calientamiento y fuerza/competición.
- Se fija la plantilla exacta de valores neutros para fuerza.
- Se incorpora la fórmula robusta de VMED con `@ESERR`.
- Se documenta la fórmula esperada de VMAX y queda pendiente su confirmación literal.
- Se establece que las fórmulas se parametrizan con la fila actual de la clave.

# 30. Cambios de la versión 0.5

- Se confirma la fórmula definitiva de `VMAX M/S` con referencias `F/E`.
- Se elimina la duplicidad de `CMP`.
- `CMP` queda reservado para competición de velocidad/calentamiento.
- `CMF` se crea para competición de fuerza.
- `CMP` pasa a la familia de calentamiento/carrera.
- `CMF` pasa a la familia de fuerza.
- La disposición actual observada es `CMF` en la fila 36 y `CMP` en la fila 51.
