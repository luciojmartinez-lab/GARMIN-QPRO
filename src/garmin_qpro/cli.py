"""Minimal command-line interface for one FIT/ZIP to QPro conversion."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from garmin_qpro.conversion import (
    ActivityRequiresChoiceError,
    MultipleFitSourcesError,
)
from garmin_qpro.garmin_connect import TrainingLoadAdapterError
from garmin_qpro.input.sources import UnsupportedInputError
from garmin_qpro.input.zip_loader import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
)
from garmin_qpro.pipeline.activity_to_qpro import (
    ActivityToQProResult,
    convert_input_path_to_qpro,
)
from garmin_qpro.pipeline.garmin_load import (
    ActivityDateUnavailableForGarminLoadError,
    TrainingLoadProvider,
    convert_input_path_to_qpro_with_garmin_load,
)
from garmin_qpro.qpro.rows import UnknownQProKeyError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="garmin-qpro",
        description=(
            "Convierte un FIT o ZIP con un unico FIT en una fila TSV de "
            "25 columnas para Quattro Pro."
        ),
    )
    parser.add_argument("path", type=Path, help="archivo FIT o ZIP que convertir")
    parser.add_argument(
        "--key",
        dest="explicit_qpro_key",
        metavar="CLAVE",
        help="clave QPro explicita, por ejemplo ENT o PES",
    )
    parser.add_argument(
        "--no-garmin-load",
        action="store_true",
        help="no consultar Garmin Connect y dejar vacias CAG y CCR",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="mostrar metadatos de conversion en stderr",
    )
    return parser


def _display_value(value: object | None) -> str:
    return "no disponible" if value is None else str(value)


def _write_verbose(
    result: ActivityToQProResult,
    *,
    path: Path,
    stream: TextIO,
) -> None:
    metadata = result.activity_context.metadata
    cells = result.final_row.as_tuple()
    details = (
        ("archivo", path),
        ("workout_name", metadata.workout_name),
        ("sport_profile_name", metadata.sport_profile_name),
        ("activity_date", metadata.activity_date),
        ("qpro_key", result.qpro_key),
        ("family", result.family.value),
        ("CARGA", cells[18]),
        ("CARGA_AGUDA", cells[23]),
        ("CARGA_CRONICA", cells[24]),
    )
    for label, value in details:
        print(f"{label}: {_display_value(value)}", file=stream)


def _choice_error_message(error: ActivityRequiresChoiceError) -> str:
    metadata = error.activity_context.metadata
    return (
        "No se pudo determinar una clave QPro segura. "
        f"workout_name={metadata.workout_name!r}; "
        f"sport_profile_name={metadata.sport_profile_name!r}; "
        f"motivo={error.reason}. Repita el comando con --key XXX."
    )


def _multiple_sources_message(error: MultipleFitSourcesError) -> str:
    names = ", ".join(source.source_name for source in error.sources)
    return (
        f"La entrada contiene {len(error.sources)} fuentes FIT: {names}. "
        "Esta CLI convierte exactamente una actividad cada vez."
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    adapter: TrainingLoadProvider | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return a process exit status."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    arguments = _parser().parse_args(argv)

    try:
        if arguments.no_garmin_load:
            result = convert_input_path_to_qpro(
                arguments.path,
                explicit_qpro_key=arguments.explicit_qpro_key,
            )
        else:
            result = convert_input_path_to_qpro_with_garmin_load(
                arguments.path,
                adapter=adapter,
                explicit_qpro_key=arguments.explicit_qpro_key,
            )
    except ActivityRequiresChoiceError as exc:
        print(f"Error: {_choice_error_message(exc)}", file=errors)
        return 2
    except MultipleFitSourcesError as exc:
        print(f"Error: {_multiple_sources_message(exc)}", file=errors)
        return 2
    except ActivityDateUnavailableForGarminLoadError:
        print(
            "Error: el FIT no contiene una fecha local fiable; Garmin Connect "
            "no fue consultado. Use --no-garmin-load solo si desea dejar CAG "
            "y CCR vacias.",
            file=errors,
        )
        return 3
    except TrainingLoadAdapterError as exc:
        print(
            f"Error de Garmin Connect: {exc}. No se genero ninguna fila.",
            file=errors,
        )
        return 3
    except UnknownQProKeyError as exc:
        print(f"Error: clave QPro desconocida: {exc.key!r}.", file=errors)
        return 2
    except (
        UnsupportedInputError,
        NoFitFilesError,
        InvalidZipError,
        UnsafeZipPathError,
    ) as exc:
        print(f"Error de entrada: {exc}", file=errors)
        return 2
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Error de conversion: {exc}", file=errors)
        return 2

    if arguments.verbose:
        _write_verbose(result, path=arguments.path, stream=errors)
    print(result.tsv, file=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point."""

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
