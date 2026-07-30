"""Secure desktop Garmin session management."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import (
    GarminAuthenticationError,
    GarminConnectionError,
    GarminCredentialStoreError,
    GarminIntegrationUnavailableError,
    GarminInvalidSessionError,
    GarminMfaCancelledError,
)
from .reader import (
    GarminConnectReader,
    _load_garmin_bindings,
    _raise_remote_error,
)

DEFAULT_DESKTOP_SESSION_FILE = (
    Path.home() / ".garmin-qpro" / "desktop-session.dpapi"
)
_DPAPI_DESCRIPTION = "GARMIN-QPRO Garmin session"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


@dataclass(frozen=True, slots=True)
class StoredGarminSession:
    email: str
    token_data: str


class SessionVault(Protocol):
    def load(self) -> StoredGarminSession | None: ...

    def save(self, session: StoredGarminSession) -> None: ...

    def clear(self) -> None: ...


class DpapiProtector(Protocol):
    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, data: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _input_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


class WindowsDpapiProtector:
    """Encrypt bytes for the current Windows user with native DPAPI."""

    __slots__ = ()

    @staticmethod
    def _libraries() -> tuple[object, object]:
        if sys.platform != "win32":
            raise GarminIntegrationUnavailableError(
                "Windows DPAPI session storage is unavailable"
            )
        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        return crypt32, kernel32

    def protect(self, data: bytes) -> bytes:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        input_blob, input_buffer = _input_blob(data)
        output_blob = _DataBlob()
        crypt32, kernel32 = self._libraries()
        if not crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            _DPAPI_DESCRIPTION,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)

    def unprotect(self, data: bytes) -> bytes:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        input_blob, input_buffer = _input_blob(data)
        output_blob = _DataBlob()
        crypt32, kernel32 = self._libraries()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)


class DpapiSessionVault:
    """Store a DPAPI-encrypted Garmin session in a local file."""

    __slots__ = ("path", "protector")

    def __init__(
        self,
        *,
        path: Path = DEFAULT_DESKTOP_SESSION_FILE,
        protector: DpapiProtector | None = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.protector = protector or WindowsDpapiProtector()

    def load(self) -> StoredGarminSession | None:
        try:
            encrypted = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except Exception as exc:
            raise GarminCredentialStoreError(
                "Encrypted Garmin session could not be read"
            ) from exc
        if not encrypted:
            raise GarminInvalidSessionError(
                "Encrypted Garmin session is empty"
            )
        try:
            payload = self.protector.unprotect(encrypted).decode("utf-8")
        except Exception as exc:
            raise GarminInvalidSessionError(
                "Encrypted Garmin session could not be decrypted"
            ) from exc
        try:
            parsed = json.loads(payload)
            email = parsed["email"]
            token_data = parsed["token_data"]
            if not isinstance(email, str) or not isinstance(token_data, str):
                raise TypeError
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise GarminInvalidSessionError(
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
        ).encode("utf-8")
        try:
            encrypted = self.protector.protect(payload)
        except Exception as exc:
            raise GarminCredentialStoreError(
                "Garmin session could not be encrypted"
            ) from exc
        if not encrypted:
            raise GarminCredentialStoreError(
                "Windows DPAPI returned an empty Garmin session"
            )
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        except Exception as exc:
            raise GarminCredentialStoreError(
                "Encrypted Garmin session could not be saved"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception as exc:
            raise GarminCredentialStoreError(
                "Encrypted Garmin session could not be cleared"
            ) from exc


# Compatibility name for callers of the desktop API. It no longer uses keyring.
KeyringSessionVault = DpapiSessionVault


class GarminDesktopSession:
    """Own an authenticated client and expose only the read-only reader."""

    __slots__ = ("_client", "_reader", "_vault", "email")

    def __init__(self, vault: SessionVault | None = None) -> None:
        self._vault = vault or DpapiSessionVault()
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
            if isinstance(exc, GarminMfaCancelledError):
                raise
            try:
                _raise_remote_error(exc, bindings, operation="login")
            except GarminAuthenticationError as auth_error:
                if token_data is not None:
                    raise GarminInvalidSessionError(
                        "Stored Garmin session was rejected"
                    ) from auth_error
                raise
        self._client = client
        self._reader = GarminConnectReader(client, _bindings=bindings)
        self.email = email

    def _dump_tokens(self) -> str:
        client = self._client
        try:
            token_data = client.client.dumps()
        except Exception as exc:
            raise GarminCredentialStoreError(
                "Garmin session tokens could not be secured"
            ) from exc
        if not isinstance(token_data, str) or len(token_data) <= 512:
            raise GarminCredentialStoreError(
                "Garmin returned an invalid reusable session"
            )
        return token_data
