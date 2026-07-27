"""Decode in-memory FIT sources with the official Garmin FIT SDK."""

from garmin_fit_sdk import Decoder, Stream

from garmin_qpro.input.sources import FitSource

from .models import DecodedFit


class InvalidFitError(ValueError):
    """Raised when source bytes do not contain a valid FIT header."""


def decode_fit(
    source: FitSource,
    *,
    verify_crc: bool = True,
) -> DecodedFit:
    """Decode one source while preserving partial messages and SDK errors."""

    if not isinstance(source, FitSource):
        raise TypeError("source must be a FitSource")
    if not isinstance(verify_crc, bool):
        raise TypeError("verify_crc must be a boolean")

    stream = Stream.from_byte_array(bytearray(source.data))
    decoder = Decoder(stream)
    if not decoder.is_fit():
        raise InvalidFitError(f"Invalid FIT header: {source.source_name}")

    messages, errors = decoder.read(
        apply_scale_and_offset=True,
        convert_datetimes_to_dates=True,
        convert_types_to_strings=True,
        enable_crc_check=verify_crc,
        expand_sub_fields=True,
        expand_components=True,
        merge_heart_rates=True,
    )
    return DecodedFit(
        source=source,
        messages=messages,
        errors=errors,
        crc_checked=verify_crc,
    )
