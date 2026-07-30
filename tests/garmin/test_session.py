from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from garmin_qpro.garmin import session as session_module
from garmin_qpro.garmin.errors import (
    GarminAuthenticationError,
    GarminChallengeError,
    GarminConnectionError,
    GarminCredentialStoreError,
    GarminInvalidSessionError,
    GarminRateLimitError,
)
from garmin_qpro.garmin.reader import _GarminBindings
from garmin_qpro.garmin.session import (
    DpapiSessionVault,
    GarminDesktopSession,
    KeyringSessionVault,
    StoredGarminSession,
    WindowsDpapiProtector,
)


class ExternalAuthenticationError(Exception):
    pass


class ExternalConnectionError(Exception):
    pass


class ExternalRateLimitError(Exception):
    pass


class ExternalAuthenticationChallengeError(ExternalAuthenticationError):
    status_code = 403


class FakeVault:
    def __init__(self, stored: StoredGarminSession | None = None) -> None:
        self.stored = stored
        self.saved: StoredGarminSession | None = None
        self.clear_count = 0

    def load(self) -> StoredGarminSession | None:
        return self.stored

    def save(self, session: StoredGarminSession) -> None:
        self.saved = session
        self.stored = session

    def clear(self) -> None:
        self.clear_count += 1
        self.stored = None


class FakeDpapiProtector:
    prefix = b"DPAPI-TEST\x00"

    def protect(self, data: bytes) -> bytes:
        return self.prefix + bytes(value ^ 0xA5 for value in data)

    def unprotect(self, data: bytes) -> bytes:
        if not data.startswith(self.prefix):
            raise OSError("invalid encrypted payload")
        return bytes(value ^ 0xA5 for value in data[len(self.prefix):])


def _install_bindings(monkeypatch, *, login_error: Exception | None = None):
    observed: dict[str, object] = {}
    token_data = "{" + ("x" * 600) + "}"

    class FakeGarmin:
        class ActivityDownloadFormat:
            ORIGINAL = object()

        def __init__(self, *, email=None, password=None, prompt_mfa=None):
            observed["email"] = email
            observed["password"] = password
            observed["prompt_mfa"] = prompt_mfa
            self.client = SimpleNamespace(dumps=lambda: token_data)

        def login(self, tokenstore=None):
            observed["tokenstore"] = tokenstore
            if login_error:
                raise login_error

        def logout(self):
            observed["logout"] = True

    bindings = _GarminBindings(
        Garmin=FakeGarmin,
        authentication_error=ExternalAuthenticationError,
        connection_error=ExternalConnectionError,
        too_many_requests_error=ExternalRateLimitError,
    )
    monkeypatch.setattr(
        session_module,
        "_load_garmin_bindings",
        lambda: bindings,
    )
    return observed, token_data


def test_connect_saves_only_email_and_reusable_tokens(monkeypatch) -> None:
    observed, token_data = _install_bindings(monkeypatch)
    vault = FakeVault()
    session = GarminDesktopSession(vault)
    callback = lambda: "123456"

    session.connect(
        email="user@example.com",
        password="private-password",
        prompt_mfa=callback,
    )

    assert session.connected is True
    assert session.email == "user@example.com"
    assert observed["password"] == "private-password"
    assert observed["prompt_mfa"] is callback
    assert vault.saved == StoredGarminSession(
        email="user@example.com",
        token_data=token_data,
    )
    assert "private-password" not in repr(session)
    assert "private-password" not in repr(vault.saved)


def test_restore_uses_secure_token_without_password(monkeypatch) -> None:
    observed, token_data = _install_bindings(monkeypatch)
    session = GarminDesktopSession(
        FakeVault(StoredGarminSession("user@example.com", token_data))
    )

    assert session.restore() is True
    assert observed["email"] is None
    assert observed["password"] is None
    assert observed["tokenstore"] == token_data


def test_restore_without_saved_session_works_offline(monkeypatch) -> None:
    session = GarminDesktopSession(FakeVault())

    assert session.restore() is False
    assert session.connected is False


def test_disconnect_clears_memory_and_vault(monkeypatch) -> None:
    _observed, _token_data = _install_bindings(monkeypatch)
    vault = FakeVault()
    session = GarminDesktopSession(vault)
    session.connect(email="u@example.com", password="secret")

    session.disconnect()

    assert session.connected is False
    assert session.email is None
    assert vault.clear_count == 1


def test_authentication_errors_never_include_credentials(monkeypatch) -> None:
    _install_bindings(
        monkeypatch,
        login_error=ExternalAuthenticationError("private-password"),
    )
    session = GarminDesktopSession(FakeVault())

    with pytest.raises(GarminAuthenticationError) as exc_info:
        session.connect(email="u@example.com", password="private-password")

    assert "private-password" not in str(exc_info.value)


def test_connection_errors_never_include_tokens(monkeypatch) -> None:
    token_data = "{" + ("secret-token" * 60) + "}"
    _install_bindings(
        monkeypatch,
        login_error=ExternalConnectionError(token_data),
    )
    session = GarminDesktopSession(
        FakeVault(StoredGarminSession("u@example.com", token_data))
    )

    with pytest.raises(GarminConnectionError) as exc_info:
        session.restore()

    assert "secret-token" not in str(exc_info.value)


def test_rejected_saved_tokens_have_a_specific_error(monkeypatch) -> None:
    _observed, token_data = _install_bindings(
        monkeypatch,
        login_error=ExternalAuthenticationError("rejected token"),
    )
    session = GarminDesktopSession(
        FakeVault(StoredGarminSession("u@example.com", token_data))
    )

    with pytest.raises(GarminInvalidSessionError):
        session.restore()


def test_rate_limit_during_restore_is_not_reported_as_invalid_tokens(
    monkeypatch,
) -> None:
    _observed, token_data = _install_bindings(
        monkeypatch,
        login_error=ExternalRateLimitError("429"),
    )
    session = GarminDesktopSession(
        FakeVault(StoredGarminSession("u@example.com", token_data))
    )

    with pytest.raises(GarminRateLimitError):
        session.restore()


def test_security_challenge_during_restore_is_not_reported_as_invalid_tokens(
    monkeypatch,
) -> None:
    _observed, token_data = _install_bindings(
        monkeypatch,
        login_error=ExternalAuthenticationChallengeError("Cloudflare CAPTCHA"),
    )
    session = GarminDesktopSession(
        FakeVault(StoredGarminSession("u@example.com", token_data))
    )

    with pytest.raises(GarminChallengeError):
        session.restore()


def test_dpapi_vault_handles_large_sessions_without_plaintext(tmp_path) -> None:
    path = tmp_path / "desktop-session.dpapi"
    vault = DpapiSessionVault(
        path=path,
        protector=FakeDpapiProtector(),
    )
    stored = StoredGarminSession(
        "user@example.com",
        "large-private-token-" * 2_000,
    )

    vault.save(stored)

    assert vault.load() == stored
    encrypted = path.read_bytes()
    assert stored.email.encode() not in encrypted
    assert stored.token_data.encode() not in encrypted
    assert not list(tmp_path.glob("*.tmp"))
    vault.clear()
    assert vault.load() is None


def test_keyring_compatibility_name_uses_dpapi_vault() -> None:
    assert KeyringSessionVault is DpapiSessionVault


def test_dpapi_vault_rejects_corrupt_encrypted_session(tmp_path) -> None:
    path = tmp_path / "desktop-session.dpapi"
    path.write_bytes(b"not-dpapi")
    vault = DpapiSessionVault(
        path=path,
        protector=FakeDpapiProtector(),
    )

    with pytest.raises(GarminInvalidSessionError):
        vault.load()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_windows_dpapi_round_trip_is_encrypted(tmp_path) -> None:
    path = tmp_path / "desktop-session.dpapi"
    vault = DpapiSessionVault(
        path=path,
        protector=WindowsDpapiProtector(),
    )
    stored = StoredGarminSession(
        "native@example.com",
        "native-private-token-" * 1_000,
    )

    vault.save(stored)

    encrypted = path.read_bytes()
    assert vault.load() == stored
    assert stored.email.encode() not in encrypted
    assert stored.token_data.encode() not in encrypted


def test_dpapi_vault_reports_atomic_write_failure(
    monkeypatch,
    tmp_path,
) -> None:
    path = tmp_path / "desktop-session.dpapi"
    vault = DpapiSessionVault(
        path=path,
        protector=FakeDpapiProtector(),
    )

    def fail_replace(_source, _target) -> None:
        raise OSError("blocked")

    monkeypatch.setattr(
        session_module.os,
        "replace",
        fail_replace,
    )

    with pytest.raises(GarminCredentialStoreError):
        vault.save(StoredGarminSession("u@example.com", "token-data"))

    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_session_does_not_emit_credentials_to_logs(monkeypatch, caplog) -> None:
    _install_bindings(monkeypatch)
    session = GarminDesktopSession(FakeVault())

    session.connect(email="u@example.com", password="private-password")

    assert "private-password" not in caplog.text


def test_token_dump_failure_is_reported_as_credential_store_error(
    monkeypatch,
) -> None:
    observed, _token_data = _install_bindings(monkeypatch)
    vault = FakeVault()
    session = GarminDesktopSession(vault)

    class BrokenClient:
        def dumps(self):
            raise OSError("private-token")

    original_garmin = session_module._load_garmin_bindings
    bindings = original_garmin()
    original_type = bindings.Garmin

    class BrokenGarmin(original_type):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.client = BrokenClient()

    monkeypatch.setattr(
        session_module,
        "_load_garmin_bindings",
        lambda: type(bindings)(
            Garmin=BrokenGarmin,
            authentication_error=bindings.authentication_error,
            connection_error=bindings.connection_error,
            too_many_requests_error=bindings.too_many_requests_error,
        ),
    )

    with pytest.raises(GarminCredentialStoreError):
        session.connect(email="u@example.com", password="private-password")

    assert observed["password"] == "private-password"
