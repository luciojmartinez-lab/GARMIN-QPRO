from garmin_qpro.qpro.row import QProRow, build_force_row
from garmin_qpro.qpro.schema import QPRO_COLUMNS
from garmin_qpro.qpro.tsv import row_to_tsv, rows_to_tsv


def test_row_to_tsv_has_exactly_25_columns_and_24_tabs() -> None:
    row = build_force_row("PES", 61)
    output = row_to_tsv(row)

    assert output.count("\t") == 24
    assert len(output.split("\t")) == 25


def test_row_to_tsv_has_no_header_or_trailing_tab_or_newline() -> None:
    row = build_force_row("CMF", 36, chronic_load=245)
    output = row_to_tsv(row)

    assert not output.startswith("\t".join(QPRO_COLUMNS))
    assert output.split("\t", maxsplit=1)[0] == "CMF"
    assert not output.endswith("\t")
    assert not output.endswith("\n")


def test_row_to_tsv_does_not_add_wrapping_quotes() -> None:
    row = QProRow(["PES", *("" for _ in range(24))])
    output = row_to_tsv(row)

    assert not output.startswith('"')
    assert not output.endswith('"')


def test_rows_to_tsv_joins_rows_with_newlines() -> None:
    first = build_force_row("PES", 61)
    second = build_force_row("CMF", 36)
    output = rows_to_tsv([first, second])

    assert output == f"{row_to_tsv(first)}\n{row_to_tsv(second)}"
    assert output.count("\n") == 1
    assert not output.endswith("\n")


def test_rows_to_tsv_accepts_generators() -> None:
    rows = (build_force_row(key, row) for key, row in [("PES", 61)])
    assert rows_to_tsv(rows) == row_to_tsv(build_force_row("PES", 61))


def test_rows_to_tsv_empty_collection_is_empty() -> None:
    assert rows_to_tsv([]) == ""
