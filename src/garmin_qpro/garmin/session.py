"""Secure desktop Garmin session management."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .errors import (
    GarminAuthenticationError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
)
from .reader import (
    GarminConnectReader,
    _load_garmin_bindings,
    _raise_remote_error,
)

KEYRING_SERVICE = "GARMIN-QPRO"
KEYRING_ACCOUNT = "garmin-connect-session"


@dataclass(frozen=True, slots=True)
class StoredGarminSession:
    email: str
    token_data: str


class SessionVault(Protocol):
    def load(self) -> StoredGarminSession | None: ...

    def save(self, session: StoredGarminSession) -> None: ...

    def clear(self) -> None: ...


class KeyringSessionVault:
    """Store Garmin tokens in the OS credential vault, never in the repository."""

    __slots__ = ("account", "service")

    def __init__(
        self,
        *,
        service: str = KEYRING_SERVICE,
        account: str = KEYRING_ACCOUNT,
    ) -> None:
        self.service = service
        self.account = account

    @staticmethod
    def _keyring() -> object:
        try:
            keyring = importlib.import_module("keyring")
        except ImportError as exc:
            raise GarminIntegrationUnavailableError(
                'Secure session storage is unavailable; install ".[desktop]"'
            ) from exc
        if sys.platform == "win32" and hasattr(keyring, "set_keyring"):
            try:
                windows = importlib.import_module("keyring.backends.Windows")
                keyring.set_keyring(windows.WinVaultKeyring())
            except (AttributeError, ImportError) as exc:
                raise GarminIntegrationUnavailableError(
                    "Windows credential storage is unavailable"
                ) from exc
        return keyring

    def load(self) -> StoredGarminSession | None:
        keyring = self._keyring()
        try:
            payload = keyring.get_password(self.service, self.account)
        except Exception as exc:
            raise GarminConnectionError(
                "Windows credential storage could not be read"
            ) from exc
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
            email = parsed["email"]
            token_data = parsed["token_data"]
            if not isinstance(email, str) or not isinstance(token_data, str):
                raise TypeError
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise GarminAuthenticationError(
                "Stored Garmin session is invalid"
            ) from exc
        return StoredGarminSession(email=email, token_data=token_data)

    def save(self, session: StoredGarminSession) -> None:
        if not isinstance(session, StoredGarminSession):
            raise TypeError("session must be a StoredGarminSession")
        payload = json.dumps(
            {"email": session.email, "token_data": session.token_data},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        keyring = self._keyring()
        try:
            keyring.set_password(self.service, self.account, payload)
        except Exception as exc:
            raise GarminConnectionError(
                "Windows credential storage could not save the Garmin session"
            ) from exc

    def clear(self) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service, self.account)
        except Exception as exc:
            not_found = getattr(
                getattr(keyring, "errors", object()),
                "PasswordDeleteError",
                (),
            )
            if not_found and isinstance(exc, not_found):
                return
            raise GarminConnectionError(
                "Windows credential storage could not clear the Garmin session"
            ) from exc


class GarminDesktopSession:
    """Own an authenticated client and expose only the read-only reader."""

    __slots__ = ("_client", "_reader", "_vault", "email")

    def __init__(self, vault: SessionVault | None = None) -> None:
        self._vault = vault or KeyringSessionVault()
        self._client: object | None = None
        self._reader: GarminConnectReader | None = None
        self.email: str | None = None

    @property
    def connected(self) -> bool:
        return self._reader is not None

    @property
    def has_saved_session(self) -> bool:
        return self._vault.load() is not None

    @property
    def reader(self) -> GarminConnectReader:
        if self._reader is None:
            raise GarminAuthenticationError("Garmin is not connected")
        return self._reader

    def restore(self) -> bool:
        stored = self._vault.load()
        if stored is None:
            return False
        self._login(
            email=stored.email,
            password=None,
            token_data=stored.token_data,
            prompt_mfa=None,
        )
        return True

    def connect(
        self,
        *,
        email: str,
        password: str,
        prompt_mfa: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(email, str) or not email.strip():
            raise ValueError("email cannot be empty")
        if not isinstance(password, str) or not password:
            raise ValueError("password cannot be empty")
        if prompt_mfa is not None and not callable(prompt_mfa):
            raise TypeError("prompt_mfa must be callable or None")
        self._login(
            email=email.strip(),
            password=password,
            token_data=None,
            prompt_mfa=prompt_mfa,
        )
        token_data = self._dump_tokens()
        self._vault.save(
            StoredGarminSession(email=email.strip(), token_data=token_data)
        )

    def disconnect(self) -> None:
        client = self._client
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
        self._client = None
        self._reader = None
        self.email = None
        self._vault.clear()

    def _login(
        self,
        *,
        email: str,
        password: str | None,
        token_data: str | None,
        prompt_mfa: Callable[[], str] | None,
    ) -> None:
        bindings = _load_garmin_bindings()
        try:
            client = bindings.Garmin(
                email=email if password is not None else None,
                password=password,
                prompt_mfa=prompt_mfa,
            )
            if token_data is None:
                client.login()
            else:
                client.login(tokenstore=token_data)
        except Exception as exc:
            _raise_remote_error(exc, bindings, operation="login")
        self._client = client
        self._reader = GarminConnectReader(client, _bindings=bindings)
        self.email = email

    def _dump_tokens(self) -> str:
        client = self._client
        try:
            token_data = client.client.dumps()
        except Exception as exc:
            raise GarminConnectionError(
                "Garmin session tokens could not be secured"
            ) from exc
        if not isinstance(token_data, str) or len(token_data) <= 512:
            raise GarminConnectionError(
                "Garmin returned an invalid reusable session"
            )
        return token_data
