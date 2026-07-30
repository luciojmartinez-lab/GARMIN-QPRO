from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from garmin_qpro.desktop.dialogs import (
    LOGIN_DIALOG_HEIGHT,
    LOGIN_DIALOG_WIDTH,
    LoginCredentials,
)


def test_login_dialog_is_wider_than_the_previous_simple_prompt() -> None:
    assert LOGIN_DIALOG_WIDTH >= 600
    assert LOGIN_DIALOG_HEIGHT >= 360


def test_login_credentials_are_immutable() -> None:
    credentials = LoginCredentials("user@example.com", "private-password")

    with pytest.raises(FrozenInstanceError):
        credentials.password = "changed"  # type: ignore[misc]
