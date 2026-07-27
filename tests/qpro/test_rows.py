import pytest

from garmin_qpro.qpro.rows import (
    CURRENT_ROW_HINTS,
    FORCE_KEYS,
    RUNNING_KEYS,
    QProFamily,
    UnknownQProKeyError,
    family_for_key,
    is_force_key,
    is_running_key,
)


def test_family_membership_for_definitive_keys() -> None:
    assert family_for_key("CMP") is QProFamily.RUNNING
    assert family_for_key("CMF") is QProFamily.FORCE
    assert family_for_key("ESC") is QProFamily.RUNNING


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (" cmp ", QProFamily.RUNNING),
        ("  esc", QProFamily.RUNNING),
        ("cmf  ", QProFamily.FORCE),
    ],
)
def test_keys_accept_spaces_and_lowercase(
    key: str, expected: QProFamily
) -> None:
    assert family_for_key(key) is expected


def test_family_predicates_use_the_same_classification() -> None:
    assert is_running_key(" cal ")
    assert not is_force_key(" cal ")
    assert is_force_key(" tef ")
    assert not is_running_key(" tef ")


@pytest.mark.parametrize("key", ["UNKNOWN", "", "   ", "COM"])
def test_unknown_key_raises_specific_error(key: str) -> None:
    with pytest.raises(UnknownQProKeyError):
        family_for_key(key)


def test_non_string_key_is_rejected() -> None:
    with pytest.raises(TypeError):
        family_for_key(23)  # type: ignore[arg-type]


def test_defined_families_do_not_overlap() -> None:
    assert RUNNING_KEYS.isdisjoint(FORCE_KEYS)


def test_current_row_hints_are_only_a_complete_reference_snapshot() -> None:
    assert CURRENT_ROW_HINTS["ENT"] == 23
    assert CURRENT_ROW_HINTS["CMP"] == 51
    assert CURRENT_ROW_HINTS["CMF"] == 36
    assert set(CURRENT_ROW_HINTS) == RUNNING_KEYS | FORCE_KEYS
