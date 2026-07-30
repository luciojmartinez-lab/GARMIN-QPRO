from __future__ import annotations

from types import SimpleNamespace

import pytest

from garmin_qpro.garmin.errors import (
    GarminAuthenticationError,
    GarminChallengeError,
    GarminCredentialStoreError,
    GarminIntegrationUnavailableError,
    GarminInvalidSessionError,
    GarminLoginIssue,
    GarminMfaCancelledError,
    GarminNetworkError,
    GarminRateLimitError,
    classify_login_issue,
    diagnose_login_error,
    extract_http_status,
)


class HttpFailure(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.response = SimpleNamespace(status_code=status)
        super().__init__(message)


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (
            GarminAuthenticationError("private-password"),
            GarminLoginIssue.CREDENTIALS,
        ),
        (
            GarminMfaCancelledError("private-mfa-code"),
            GarminLoginIssue.MFA,
        ),
        (
            GarminRateLimitError("429 secret-token"),
            GarminLoginIssue.RATE_LIMIT,
        ),
        (
            GarminChallengeError("cloudflare private-cookie"),
            GarminLoginIssue.CHALLENGE,
        ),
        (
            GarminNetworkError("private-network-address"),
            GarminLoginIssue.NETWORK,
        ),
        (
            GarminIntegrationUnavailableError("private-path"),
            GarminLoginIssue.INTEGRATION,
        ),
        (
            GarminCredentialStoreError("private-token"),
            GarminLoginIssue.CREDENTIAL_STORE,
        ),
        (
            GarminInvalidSessionError("private-refresh-token"),
            GarminLoginIssue.INVALID_SESSION,
        ),
    ),
)
def test_every_login_failure_has_a_distinct_safe_category(
    error: Exception,
    expected: GarminLoginIssue,
) -> None:
    diagnostic = diagnose_login_error(error)

    assert diagnostic.issue is expected
    assert diagnostic.title
    assert diagnostic.message
    assert diagnostic.action


def test_http_status_is_extracted_from_nested_response() -> None:
    cause = HttpFailure(429, "secret-token")
    wrapper = GarminNetworkError("safe")
    wrapper.__cause__ = cause

    assert extract_http_status(wrapper) == 429
    assert classify_login_issue(wrapper) is GarminLoginIssue.RATE_LIMIT
    assert diagnose_login_error(wrapper).http_status == 429


def test_cloudflare_challenge_is_detected_from_nested_http_failure() -> None:
    cause = HttpFailure(403, "Cloudflare CAPTCHA private-cookie")
    wrapper = GarminNetworkError("safe")
    wrapper.__cause__ = cause

    diagnostic = diagnose_login_error(wrapper)

    assert diagnostic.issue is GarminLoginIssue.CHALLENGE
    assert diagnostic.http_status == 403


def test_mfa_requirement_is_detected_in_wrapped_library_error() -> None:
    cause = RuntimeError("MFA verification code required: 123456")
    wrapper = GarminNetworkError("safe")
    wrapper.__cause__ = cause

    assert classify_login_issue(wrapper) is GarminLoginIssue.MFA


def test_diagnostic_is_copyable_but_never_contains_remote_text(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "garmin_qpro.garmin.errors.garminconnect_package_version",
        lambda: "0.3.7",
    )
    secret = "password token mfa-code private@example.com"
    error = GarminAuthenticationError(secret)

    diagnostic = diagnose_login_error(error)
    copied = diagnostic.technical_text

    assert copied == (
        "Tipo: GarminAuthenticationError\n"
        "HTTP: no disponible\n"
        "garminconnect: 0.3.7"
    )
    assert secret not in copied
    assert "private@example.com" not in diagnostic.message
    assert "password" not in copied.casefold()


def test_unknown_error_does_not_claim_credentials_are_wrong() -> None:
    diagnostic = diagnose_login_error(RuntimeError("private detail"))

    assert diagnostic.issue is GarminLoginIssue.UNKNOWN
    assert "credencial" not in diagnostic.message.casefold()
