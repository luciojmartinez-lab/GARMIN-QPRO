from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.desktop.dialogs import (
    GarminDiagnosticDialog,
    LOGIN_DIALOG_HEIGHT,
    LOGIN_DIALOG_WIDTH,
    LoginCredentials,
)
from garmin_qpro.garmin.errors import diagnose_login_error


class FakeParent:
    def __init__(self) -> None:
        self.state_value = "zoomed"
        self.alpha = 0.55
        self.updated = False

    def state(self, value=None):
        if value is not None:
            self.state_value = value
        return self.state_value

    def attributes(self, name, value=None):
        assert name == "-alpha"
        if value is not None:
            self.alpha = value
        return self.alpha

    def update_idletasks(self) -> None:
        self.updated = True


class FakeWidget:
    def __init__(self, _parent=None, **kwargs) -> None:
        self.command = kwargs.get("command")

    def grid(self, **_kwargs) -> None:
        pass

    def grid_columnconfigure(self, *_args, **_kwargs) -> None:
        pass

    def insert(self, *_args) -> None:
        pass

    def configure(self, **kwargs) -> None:
        if "command" in kwargs:
            self.command = kwargs["command"]

    def invoke(self) -> None:
        self.command()


class FakeWindow(FakeWidget):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.parent = parent
        self.protocols = {}
        self.bindings = {}
        self.events = []
        self.destroyed = False
        self.wait_error = None

    def title(self, _value) -> None:
        pass

    def geometry(self, _value) -> None:
        pass

    def minsize(self, *_value) -> None:
        pass

    def transient(self, _parent) -> None:
        pass

    def grab_set(self) -> None:
        self.events.append("grab_set")

    def grab_current(self):
        return None if self.destroyed else self

    def grab_release(self) -> None:
        self.events.append("grab_release")

    def protocol(self, name, callback=None):
        if callback is not None:
            self.protocols[name] = callback
        return self.protocols.get(name)

    def bind(self, name, callback) -> None:
        self.bindings[name] = callback

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def destroy(self) -> None:
        self.events.append("destroy")
        self.destroyed = True

    def wait_window(self) -> None:
        if self.wait_error is not None:
            raise self.wait_error


def _patch_dialog_widgets(monkeypatch) -> None:
    monkeypatch.setattr(
        "garmin_qpro.desktop.dialogs.ctk.CTkToplevel",
        FakeWindow,
    )
    for name in ("CTkLabel", "CTkFrame", "CTkTextbox", "CTkButton"):
        monkeypatch.setattr(
            f"garmin_qpro.desktop.dialogs.ctk.{name}",
            FakeWidget,
        )


def _diagnostic_dialog(monkeypatch):
    _patch_dialog_widgets(monkeypatch)
    parent = FakeParent()
    dialog = GarminDiagnosticDialog(
        parent,
        diagnose_login_error(RuntimeError("private")),
    )
    return dialog, parent


def test_login_dialog_is_wider_than_the_previous_simple_prompt() -> None:
    assert LOGIN_DIALOG_WIDTH >= 600
    assert LOGIN_DIALOG_HEIGHT >= 360


def test_login_credentials_are_immutable() -> None:
    credentials = LoginCredentials("user@example.com", "private-password")

    with pytest.raises(FrozenInstanceError):
        credentials.password = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("route", ("button", "escape", "window_close"))
def test_diagnostic_dialog_all_close_routes_restore_parent(
    monkeypatch,
    route: str,
) -> None:
    dialog, parent = _diagnostic_dialog(monkeypatch)

    if route == "button":
        dialog.close_button.invoke()
    elif route == "escape":
        dialog.window.bindings["<Escape>"](None)
    else:
        dialog.window.protocols["WM_DELETE_WINDOW"]()

    assert dialog.window.events[-2:] == ["grab_release", "destroy"]
    assert parent.state_value == "zoomed"
    assert parent.alpha == 1.0
    assert parent.updated is True


def test_diagnostic_dialog_show_restores_parent_in_finally(
    monkeypatch,
) -> None:
    dialog, parent = _diagnostic_dialog(monkeypatch)
    dialog.window.wait_error = RuntimeError("wait failed")

    with pytest.raises(RuntimeError, match="wait failed"):
        dialog.show()

    assert dialog.window.events[-2:] == ["grab_release", "destroy"]
    assert parent.alpha == 1.0
