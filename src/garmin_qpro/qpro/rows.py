"""Classification of Quattro Pro keys by functional family."""

from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping


class QProFamily(Enum):
    """Functional families selected exclusively from the column A key."""

    RUNNING = "RUNNING"
    FORCE = "FORCE"


class UnknownQProKeyError(ValueError):
    """Raised when a column A key has no defined functional family."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Unknown Quattro Pro key: {key!r}")


RUNNING_KEYS: Final[frozenset[str]] = frozenset(
    {
        "CAL",
        "CLP",
        "ENT",
        "CAR",
        "SER",
        "REC",
        "TEC",
        "FIN",
        "FPN",
        "AQG",
        "PLY",
        "CMP",
        "CAM",
        "FLK",
        "BIC",
        "MOV",
        "ESC",
    }
)

FORCE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "TEF",
        "MUL",
        "CMF",
        "EST",
        "TST",
        "PES",
        "BMD",
        "MOF",
        "CIR",
        "ESF",
    }
)

QPRO_FAMILY_BY_KEY: Final[Mapping[str, QProFamily]] = MappingProxyType(
    {
        **{key: QProFamily.RUNNING for key in RUNNING_KEYS},
        **{key: QProFamily.FORCE for key in FORCE_KEYS},
    }
)

# Snapshot of visible row positions for human guidance only. These values must
# never be used to classify a key or as permanent row-selection logic.
CURRENT_ROW_HINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "CAL": 18,
        "CLP": 20,
        "ENT": 23,
        "CAR": 25,
        "SER": 27,
        "REC": 29,
        "TEC": 31,
        "TEF": 32,
        "MUL": 34,
        "CMF": 36,
        "EST": 38,
        "FIN": 41,
        "FPN": 44,
        "AQG": 47,
        "PLY": 49,
        "CMP": 51,
        "TST": 53,
        "CAM": 55,
        "FLK": 57,
        "BIC": 59,
        "PES": 61,
        "BMD": 63,
        "MOV": 65,
        "MOF": 66,
        "ESC": 68,
        "ESF": 69,
        "CIR": 71,
    }
)


def _normalize_key(key: str) -> str:
    if not isinstance(key, str):
        raise TypeError("key must be a string")
    return key.strip().upper()


def family_for_key(key: str) -> QProFamily:
    """Return the family associated with a normalized column A key."""

    normalized_key = _normalize_key(key)
    try:
        return QPRO_FAMILY_BY_KEY[normalized_key]
    except KeyError:
        raise UnknownQProKeyError(key) from None


def is_running_key(key: str) -> bool:
    """Return whether a known key belongs to the running family."""

    return family_for_key(key) is QProFamily.RUNNING


def is_force_key(key: str) -> bool:
    """Return whether a known key belongs to the force family."""

    return family_for_key(key) is QProFamily.FORCE
