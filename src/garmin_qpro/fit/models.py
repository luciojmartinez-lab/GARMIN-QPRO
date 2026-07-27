"""Immutable decoded FIT results."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from garmin_qpro.input.sources import FitSource


def _freeze_collection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_collection(nested_value)
                for key, nested_value in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_collection(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_collection(item) for item in value)
    return value


def _canonical_message_type(message_type: str) -> str:
    suffix = "_mesgs"
    if message_type.endswith(suffix):
        return message_type[: -len(suffix)]
    return message_type


@dataclass(frozen=True, slots=True)
class DecodedFit:
    """Decoded messages and errors preserved as immutable collections."""

    source: FitSource
    messages: Mapping[str, tuple[Any, ...]]
    errors: tuple[Any, ...]
    crc_checked: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, FitSource):
            raise TypeError("source must be a FitSource")
        if not isinstance(self.messages, Mapping):
            raise TypeError("messages must be grouped in a mapping")
        if not isinstance(self.crc_checked, bool):
            raise TypeError("crc_checked must be a boolean")

        grouped_messages: dict[str, list[Any]] = {}
        for message_type, message_group in self.messages.items():
            canonical_type = _canonical_message_type(message_type)
            grouped_messages.setdefault(canonical_type, []).extend(
                _freeze_collection(message) for message in message_group
            )

        frozen_messages = MappingProxyType(
            {
                message_type: tuple(message_group)
                for message_type, message_group in grouped_messages.items()
            }
        )
        frozen_errors = tuple(
            _freeze_collection(error) for error in self.errors
        )
        object.__setattr__(self, "messages", frozen_messages)
        object.__setattr__(self, "errors", frozen_errors)

    def get_messages(self, message_type: str) -> tuple[Any, ...]:
        """Return an immutable message group or an empty tuple."""

        return self.messages.get(message_type, ())
