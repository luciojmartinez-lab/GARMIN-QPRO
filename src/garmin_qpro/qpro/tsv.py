"""TSV serialization for immutable Quattro Pro rows."""

from collections.abc import Iterable

from .row import QProRow


def row_to_tsv(row: QProRow) -> str:
    """Serialize one row without a header or trailing line break."""

    if not isinstance(row, QProRow):
        raise TypeError("row must be a QProRow")
    return "\t".join(row.as_tuple())


def rows_to_tsv(rows: Iterable[QProRow]) -> str:
    """Serialize rows separated by newlines, without a final newline."""

    return "\n".join(row_to_tsv(row) for row in rows)
