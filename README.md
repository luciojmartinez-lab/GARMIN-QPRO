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
- Conexion opcional y de solo lectura con Garmin Connect.

En esta fase la aplicacion no escribe automaticamente archivos TSV ni modifica
la hoja de Quattro Pro. Las descargas originales de Garmin permanecen en
memoria y tampoco se escriben automaticamente.

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

## Garmin Connect opcional

El acceso oficial de Garmin esta orientado a su programa empresarial. Esta
integracion personal usa la libreria comunitaria no oficial
`python-garminconnect`, exclusivamente para leer actividades y descargar sus
originales.

La conversion local FIT/ZIP admite Python 3.11 o posterior. La conexion en vivo
con Garmin Connect requiere Python 3.12 o posterior y se instala aparte:

```powershell
pip install -e ".[garmin]"
```

Para listar actividades recientes:

```powershell
python scripts\garmin_connect_smoke.py --limit 10
```

Para comprobar una descarga original completamente en memoria:

```powershell
python scripts\garmin_connect_smoke.py --activity-id 123456789
```

Por defecto, los tokens se guardan fuera del repositorio en:

```text
~/.garmin-qpro/garminconnect
```

El token equivale a una credencial y no debe compartirse. La aplicacion no
guarda la contrasena. Todavia no escribe FIT ni TSV automaticamente y no
incluye un servidor MCP.
