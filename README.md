# GARMIN-QPRO

Aplicacion Python para convertir actividades Garmin FIT en filas compatibles
con una hoja de entrenamiento de Quattro Pro.

## Funcionalidad actual

- Carga segura de archivos FIT y ZIP sin extraccion fisica.
- Conversion individual de actividades de carrera y fuerza.
- Conversion por lotes de varios FIT o ZIP.
- Procesamiento directo de los FIT y ZIP de una carpeta.
- Salida TSV en memoria con 23 columnas por actividad.
- Conservacion de los fallos parciales sin detener el resto del lote.

En esta fase la aplicacion no escribe automaticamente archivos TSV ni modifica
la hoja de Quattro Pro.

## Uso desde Python

```python
from pathlib import Path

from garmin_qpro import convert_input_directory

row_numbers = {
    "CAL": 18,
    "ENT": 23,
    "CMF": 36,
    "FIN": 41,
}

batch = convert_input_directory(
    Path("data/private/entrada"),
    row_numbers=row_numbers,
)

print(batch.tsv)
```

`row_numbers` configura las filas actuales de la hoja del usuario. Estos
valores se proporcionan expresamente y no se obtienen automaticamente de
`CURRENT_ROW_HINTS`.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
