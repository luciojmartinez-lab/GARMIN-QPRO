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
guarda la contrasena y todavia no escribe FIT ni TSV automaticamente.

## Servidor MCP local

GARMIN-QPRO incluye un servidor MCP opcional y exclusivamente de lectura. Usa
transporte STDIO para conectar un cliente Codex del mismo ordenador con Garmin
Connect y el conversor existente.

Instalacion:

```powershell
pip install -e ".[mcp]"
```

La autenticacion inicial o renovacion de tokens se realiza fuera de MCP:

```powershell
python scripts\garmin_connect_smoke.py --limit 10
```

Comprobacion del servidor y listado de actividades:

```powershell
python scripts\mcp_stdio_smoke.py --limit 10
```

El servidor se ejecuta internamente mediante:

```powershell
python -m garmin_qpro.mcp_server
```

Ejecutarlo directamente no abre una interfaz. El proceso queda esperando
mensajes MCP por la entrada estandar y reserva la salida estandar para el
protocolo.

El ejecutable verificado del entorno virtual de este proyecto es:

```text
C:\Users\lucio\Documents\Codex\GARMIN-QPRO\.venv\Scripts\python.exe
```

Para registrarlo en Codex:

```powershell
codex mcp add garmin-qpro -- "C:\Users\lucio\Documents\Codex\GARMIN-QPRO\.venv\Scripts\python.exe" -m garmin_qpro.mcp_server
codex mcp list
```

Reinicia el cliente de Codex despues de anadir el servidor.

Ejemplos de solicitudes:

```text
Muestrame mis diez actividades recientes de Garmin.
```

```text
Inspecciona la actividad 23662199706.
```

```text
Convierte la actividad 23662199706 usando la fila 23.
```

```text
Convierte la actividad indicada como CMF usando la fila 36.
```

Codex no debe inventar la fila. Las claves desconocidas requieren una eleccion
del usuario y `CURRENT_ROW_HINTS` no se consulta automaticamente. Las descargas
permanecen en memoria y todavia no se escribe directamente en Quattro Pro.

Este MCP local funciona con clientes Codex ejecutados en el mismo ordenador.
ChatGPT web no puede utilizar directamente esta configuracion local. Una
integracion web futura requeriria un plugin y un servidor MCP remoto mediante
HTTPS.
