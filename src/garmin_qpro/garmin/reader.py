"""Optional, read-only access to personal Garmin Connect activity data."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import ModuleType

from garmin_qpro.input.zip_loader import load_zip_fit_sources_bytes

from .errors import (
    GarminAuthenticationError,
    GarminChallengeError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminNetworkError,
    GarminRateLimitError,
    GarminResponseError,
    extract_http_status,
    exception_chain,
)
from .models import (
    GarminActivityDownload,
    GarminActivitySummary,
    normalize_activity_id,
)

MIN_GARMIN_PYTHON = (3, 12)
DEFAULT_TOKEN_STORE = Path.home() / ".garmin-qpro" / "garminconnect"


@dataclass(frozen=True, slots=True)
class _GarminBindings:
    Garmin: type
    authentication_error: type[BaseException]
    connection_error: type[BaseException]
    too_many_requests_error: type[BaseException]


def _load_garmin_bindings() -> _GarminBindings:
    if sys.version_info < MIN_GARMIN_PYTHON:
        raise GarminIntegrationUnavailableError(
            "Live Garmin Connect access requires Python 3.12 or later"
        )
    try:
        module: ModuleType = importlib.import_module("garminconnect")
        return _GarminBindings(
            Garmin=module.Garmin,
            authentication_error=module.GarminConnectAuthenticationError,
            connection_error=module.GarminConnectConnectionError,
            too_many_requests_error=module.GarminConnectTooManyRequestsError,
        )
    except (ImportError, AttributeError) as exc:
        raise GarminIntegrationUnavailableError(
            'Garmin Connect support is unavailable; install ".[garmin]"'
        ) from exc


def _raise_remote_error(
    exc: Exception,
    bindings: _GarminBindings,
    *,
    operation: str,
) -> None:
    if isinstance(exc, GarminConnectionError):
        raise exc
    status = extract_http_status(exc)
    text = " ".join(str(item) for item in exception_chain(exc)).casefold()
    if isinstance(exc, bindings.too_many_requests_error):
        raise GarminRateLimitError(
            "Garmin Connect rate limit exceeded"
        ) from exc
    if status == 429:
        raise GarminRateLimitError(
            "Garmin Connect rate limit exceeded"
        ) from exc
    if status in {403, 503} and any(
        marker in text
        for marker in ("cloudflare", "captcha", "challenge", "bot", "access denied")
    ):
        raise GarminChallengeError(
            "Garmin Connect security challenge blocked the request"
        ) from exc
    if isinstance(exc, bindings.authentication_error) or status == 401:
        raise GarminAuthenticationError(
            "Garmin Connect authentication failed"
        ) from exc
    if isinstance(exc, bindings.connection_error):
        raise GarminNetworkError(
            f"Garmin Connect {operation} failed"
        ) from exc
    raise GarminNetworkError(
        f"Garmin Connect {operation} failed"
    ) from exc


def _validate_page_value(
    value: int,
    *,
    field_name: str,
    allow_zero: bool,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0 or (not allow_zero and value == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field_name} must be {qualifier}")
    return value


class GarminConnectReader:
    """A deliberately small read-only facade over an authenticated client."""

    __slots__ = ("_bindings", "_client")

    def __init__(
        self,
        client: object,
        *,
        _bindings: _GarminBindings | None = None,
    ) -> None:
        if client is None:
            raise TypeError("client cannot be None")
        self._client = client
        self._bindings = _bindings or _load_garmin_bindings()

    def list_activities(
        self,
        *,
        start: int = 0,
        limit: int = 20,
    ) -> tuple[GarminActivitySummary, ...]:
        """Return only the minimal summary fields for recent activities."""

        validated_start = _validate_page_value(
            start,
            field_name="start",
            allow_zero=True,
        )
        validated_limit = _validate_page_value(
            limit,
            field_name="limit",
            allow_zero=False,
        )
        try:
            response = self._client.get_activities(
                validated_start,
                validated_limit,
            )
        except Exception as exc:
            _raise_remote_error(
                exc,
                self._bindings,
                operation="activity listing",
            )

        if not isinstance(response, (list, tuple)):
            raise GarminResponseError(
                "Garmin Connect returned an invalid activity list"
            )

        summaries: list[GarminActivitySummary] = []
        for index, activity in enumerate(response):
            if not isinstance(activity, Mapping):
                raise GarminResponseError(
                    f"Garmin activity {index} is not an object"
                )
            try:
                summaries.append(GarminActivitySummary.from_mapping(activity))
            except (TypeError, ValueError) as exc:
                raise GarminResponseError(
                    f"Garmin activity {index} has invalid summary fields"
                ) from exc
        return tuple(summaries)

    def download_original_activity(
        self,
        activity_id: str | int,
    ) -> GarminActivityDownload:
        """Download and inspect an original activity ZIP entirely in memory."""

        normalized_id = normalize_activity_id(activity_id)
        original_format = self._bindings.Garmin.ActivityDownloadFormat.ORIGINAL
        try:
            archive_data = self._client.download_activity(
                normalized_id,
                dl_fmt=original_format,
            )
        except Exception as exc:
            _raise_remote_error(
                exc,
                self._bindings,
                operation="activity download",
            )

        if not isinstance(archive_data, bytes) or not archive_data:
            raise GarminResponseError(
                "Garmin Connect returned an empty or invalid original archive"
            )

        container_name = f"garmin-{normalized_id}.zip"
        sources = load_zip_fit_sources_bytes(
            archive_data,
            container_name=container_name,
        )
        return GarminActivityDownload(
            activity_id=normalized_id,
            container_name=container_name,
            archive_sha256=sha256(archive_data).hexdigest(),
            archive_size=len(archive_data),
            sources=sources,
        )


def connect_garmin(
    *,
    token_store: Path,
    email: str | None = None,
    password: str | None = None,
    prompt_mfa: Callable[[], str] | None = None,
) -> GarminConnectReader:
    """Authenticate with local reusable tokens and return a read-only facade."""

    if prompt_mfa is not None and not callable(prompt_mfa):
        raise TypeError("prompt_mfa must be callable or None")
    bindings = _load_garmin_bindings()
    token_path = Path(token_store).expanduser()
    try:
        token_path.mkdir(parents=True, exist_ok=True)
        client = bindings.Garmin(
            email=email,
            password=password,
            prompt_mfa=prompt_mfa,
        )
        client.login(tokenstore=str(token_path))
    except Exception as exc:
        _raise_remote_error(
            exc,
            bindings,
            operation="login",
        )
    return GarminConnectReader(client, _bindings=bindings)
