from types import SimpleNamespace

import pytest

from garmin_qpro.fit import decoder as decoder_module
from garmin_qpro.fit.decoder import InvalidFitError, decode_fit
from garmin_qpro.fit.models import DecodedFit
from garmin_qpro.input.sources import FitSource

EXPECTED_READ_OPTIONS = {
    "apply_scale_and_offset": True,
    "convert_datetimes_to_dates": True,
    "convert_types_to_strings": True,
    "enable_crc_check": True,
    "expand_sub_fields": True,
    "expand_components": True,
    "merge_heart_rates": True,
}


def _source(data: bytes = b"fit-bytes") -> FitSource:
    return FitSource("activity.fit", None, None, data)


def _install_fake_sdk(
    monkeypatch,
    *,
    is_fit: bool = True,
    messages=None,
    errors=None,
):
    calls = SimpleNamespace(stream_data=None, stream=None, read_options=None)
    decoded_messages = (
        {"session": [{"sport": "running"}], "record": [{"heart_rate": 98}]}
        if messages is None
        else messages
    )
    decoded_errors = [] if errors is None else errors

    class FakeStream:
        @staticmethod
        def from_byte_array(data):
            calls.stream_data = data
            calls.stream = object()
            return calls.stream

    class FakeDecoder:
        def __init__(self, stream):
            assert stream is calls.stream

        def is_fit(self):
            return is_fit

        def read(self, **options):
            calls.read_options = options
            return decoded_messages, decoded_errors

    monkeypatch.setattr(decoder_module, "Stream", FakeStream)
    monkeypatch.setattr(decoder_module, "Decoder", FakeDecoder)
    return calls


def test_installed_sdk_rejects_invalid_fit_header() -> None:
    with pytest.raises(InvalidFitError):
        decode_fit(_source(b"not-a-fit-file"))


def test_invalid_fit_header_is_rejected_before_decoding(monkeypatch) -> None:
    calls = _install_fake_sdk(monkeypatch, is_fit=False)

    with pytest.raises(InvalidFitError):
        decode_fit(_source())

    assert calls.read_options is None


@pytest.mark.parametrize("verify_crc", [True, False])
def test_verify_crc_is_transmitted_to_sdk(monkeypatch, verify_crc: bool) -> None:
    calls = _install_fake_sdk(monkeypatch)

    decoded = decode_fit(_source(), verify_crc=verify_crc)

    assert calls.read_options["enable_crc_check"] is verify_crc
    assert decoded.crc_checked is verify_crc


def test_all_decoder_options_are_enabled(monkeypatch) -> None:
    calls = _install_fake_sdk(monkeypatch)

    decode_fit(_source())

    assert calls.read_options == EXPECTED_READ_OPTIONS


def test_source_bytes_are_passed_to_in_memory_stream(monkeypatch) -> None:
    calls = _install_fake_sdk(monkeypatch)
    source = _source(b"\x01\x02\x03")

    decode_fit(source)

    assert isinstance(calls.stream_data, bytearray)
    assert bytes(calls.stream_data) == source.data


def test_decoded_messages_are_grouped_and_accessible(monkeypatch) -> None:
    messages = {
        "session_mesgs": [{"sport": "running"}],
        "record_mesgs": [{"heart_rate": 98}, {"heart_rate": 101}],
        "lap_mesgs": [{"total_distance": 1000}],
    }
    _install_fake_sdk(monkeypatch, messages=messages)

    decoded = decode_fit(_source())

    assert decoded.get_messages("session")[0]["sport"] == "running"
    assert len(decoded.get_messages("record")) == 2
    assert decoded.get_messages("lap")[0]["total_distance"] == 1000
    assert decoded.get_messages("event") == ()


def test_sdk_errors_and_valid_messages_are_both_preserved(monkeypatch) -> None:
    errors = ["CRC mismatch"]
    messages = {"session": [{"sport": "strength_training"}]}
    _install_fake_sdk(monkeypatch, messages=messages, errors=errors)

    decoded = decode_fit(_source())

    assert decoded.errors == ("CRC mismatch",)
    assert decoded.get_messages("session")[0]["sport"] == "strength_training"


def test_decoded_collections_are_immutable() -> None:
    decoded = DecodedFit(
        source=_source(),
        messages={
            "record": [
                {
                    "heart_rate": 98,
                    "nested": {"values": [1, 2]},
                }
            ]
        },
        errors=[{"message": "warning"}],
        crc_checked=True,
    )

    with pytest.raises(TypeError):
        decoded.messages["lap"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        decoded.get_messages("record")[0]["heart_rate"] = 99
    with pytest.raises(TypeError):
        decoded.get_messages("record")[0]["nested"]["values"] = ()
    with pytest.raises(TypeError):
        decoded.errors[0]["message"] = "changed"

    assert isinstance(decoded.get_messages("record"), tuple)
    assert isinstance(decoded.errors, tuple)
