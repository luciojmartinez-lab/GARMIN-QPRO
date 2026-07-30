from __future__ import annotations

from types import SimpleNamespace

import pytest

from garmin_qpro.garmin import session as session_module
from garmin_qpro.garmin.errors import (
    GarminAuthenticationError,
    GarminConnectionError,
)
from garmin_qpro.garmin.reader import _GarminBindings
from garmin_qpro.garmin.session import (
    GarminDesktopSession,
    KeyringSessionVault,
    StoredGarminSession,
)


class ExternalAuthenticationError(Exception):
    pass


class ExternalConnectionError(Exception):
    pass


class ExternalRateLimitError(Exception):
    pass


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


def test_keyring_vault_serializes_without_password(monkeypatch) -> None:
    values: dict[tuple[str, str], str] = {}
    fake_keyring = SimpleNamespace(
        get_password=lambda service, account: values.get((service, account)),
        set_password=lambda service, account, value: values.__setitem__(
            (service, account), value
        ),
        delete_password=lambda service, account: values.pop((service, account)),
        errors=SimpleNamespace(PasswordDeleteError=KeyError),
    )
    monkeypatch.setattr(
        session_module.importlib,
        "import_module",
        lambda name: fake_keyring,
    )
    vault = KeyringSessionVault()
    stored = StoredGarminSession("user@example.com", "token-data")

    vault.save(stored)

    assert vault.load() == stored
    assert "password" not in next(iter(values.values())).casefold()
    vault.clear()
    assert vault.load() is None


def test_session_does_not_emit_credentials_to_logs(monkeypatch, caplog) -> None:
    _install_bindings(monkeypatch)
    session = GarminDesktopSession(FakeVault())

    session.connect(email="u@example.com", password="private-password")

    assert "private-password" not in caplog.text
