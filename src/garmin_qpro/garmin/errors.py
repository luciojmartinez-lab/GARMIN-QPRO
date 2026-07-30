"""Safe public errors and diagnostics for Garmin Connect login."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, version


class GarminLoginIssue(str, Enum):
    CREDENTIALS = "credentials_rejected"
    MFA = "mfa_required_or_cancelled"
    RATE_LIMIT = "rate_limited"
    CHALLENGE = "cloudflare_or_captcha"
    NETWORK = "network"
    INTEGRATION = "integration_unavailable"
    CREDENTIAL_STORE = "credential_store"
    INVALID_SESSION = "invalid_session"
    UNKNOWN = "unknown"


class GarminConnectionError(RuntimeError):
    """Raised when Garmin Connect cannot complete a remote operation."""


class GarminIntegrationUnavailableError(GarminConnectionError):
    """Raised when the optional integration cannot be loaded."""


class GarminAuthenticationError(GarminConnectionError):
    """Raised when Garmin Connect explicitly rejects credentials."""


class GarminMfaError(GarminAuthenticationError):
    """Raised when verification is required but cannot be completed."""


class GarminMfaCancelledError(GarminMfaError):
    """Raised when the user cancels or leaves verification empty."""


class GarminRateLimitError(GarminConnectionError):
    """Raised when Garmin temporarily limits login attempts."""


class GarminChallengeError(GarminConnectionError):
    """Raised when Cloudflare, CAPTCHA or bot protection blocks login."""


class GarminNetworkError(GarminConnectionError):
    """Raised when the remote service cannot be reached reliably."""


class GarminCredentialStoreError(GarminConnectionError):
    """Raised when Windows cannot persist or read the reusable session."""


class GarminInvalidSessionError(GarminAuthenticationError):
    """Raised when reusable Garmin tokens are absent, expired or rejected."""


class GarminResponseError(ValueError):
    """Raised when Garmin Connect returns an unusable response."""


@dataclass(frozen=True, slots=True)
class GarminLoginDiagnostic:
    issue: GarminLoginIssue
    title: str
    message: str
    action: str
    exception_type: str
    http_status: int | None
    garminconnect_version: str

    @property
    def technical_text(self) -> str:
        status = str(self.http_status) if self.http_status is not None else "no disponible"
        return (
            f"Tipo: {self.exception_type}\n"
            f"HTTP: {status}\n"
            f"garminconnect: {self.garminconnect_version}"
        )


_COPY = {
    GarminLoginIssue.CREDENTIALS: (
        "Credenciales rechazadas",
        "Garmin ha rechazado el correo o la contraseña.",
        "Comprueba los datos iniciando sesión en Garmin Connect y vuelve a intentarlo.",
    ),
    GarminLoginIssue.MFA: (
        "Verificación pendiente",
        "Garmin necesita una verificación en dos pasos que no se completó.",
        "Vuelve a conectar e introduce el código nuevo antes de que caduque.",
    ),
    GarminLoginIssue.RATE_LIMIT: (
        "Límite temporal de Garmin",
        "Garmin ha limitado temporalmente los intentos de acceso.",
        "Espera unos minutos sin repetir el acceso y vuelve a intentarlo después.",
    ),
    GarminLoginIssue.CHALLENGE: (
        "Bloqueo de seguridad de Garmin",
        "Cloudflare, un CAPTCHA o la protección automática de Garmin ha bloqueado el acceso.",
        "Abre Garmin Connect en el navegador, completa cualquier comprobación y prueba de nuevo más tarde.",
    ),
    GarminLoginIssue.NETWORK: (
        "Problema de conexión",
        "No se ha podido completar la comunicación con Garmin.",
        "Comprueba Internet, VPN, proxy y cortafuegos; después vuelve a intentarlo.",
    ),
    GarminLoginIssue.INTEGRATION: (
        "Componente Garmin no disponible",
        "La integración instalada no es compatible o le falta una dependencia.",
        "Actualiza GARMIN-QPRO o reconstruye el ejecutable con sus dependencias de escritorio.",
    ),
    GarminLoginIssue.CREDENTIAL_STORE: (
        "No se pudo guardar la sesión",
        "La conexión pudo iniciarse, pero Windows no pudo proteger la sesión reutilizable.",
        "Comprueba el Administrador de credenciales de Windows y vuelve a conectar.",
    ),
    GarminLoginIssue.INVALID_SESSION: (
        "Sesión guardada no válida",
        "La sesión guardada ha caducado o Garmin ha rechazado sus tokens.",
        "Pulsa Desconectar y vuelve a conectar con correo, contraseña y verificación si se solicita.",
    ),
    GarminLoginIssue.UNKNOWN: (
        "Acceso no completado",
        "GARMIN-QPRO no ha podido identificar con seguridad la causa.",
        "Copia el diagnóstico técnico y revisa la conexión antes de intentarlo de nuevo.",
    ),
}


def garminconnect_package_version() -> str:
    try:
        return version("garminconnect")
    except PackageNotFoundError:
        return "no disponible"


def exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return tuple(chain)


def extract_http_status(error: BaseException) -> int | None:
    for item in exception_chain(error):
        candidates = (
            getattr(item, "status_code", None),
            getattr(item, "code", None),
            getattr(getattr(item, "response", None), "status_code", None),
        )
        for candidate in candidates:
            if (
                not isinstance(candidate, bool)
                and isinstance(candidate, int)
                and 100 <= candidate <= 599
            ):
                return candidate
    return None


def _chain_text(error: BaseException) -> str:
    return " ".join(str(item) for item in exception_chain(error)).casefold()


def classify_login_issue(error: BaseException) -> GarminLoginIssue:
    chain = exception_chain(error)
    status = extract_http_status(error)
    text = _chain_text(error)

    if any(isinstance(item, GarminCredentialStoreError) for item in chain):
        return GarminLoginIssue.CREDENTIAL_STORE
    if any(isinstance(item, GarminIntegrationUnavailableError) for item in chain):
        return GarminLoginIssue.INTEGRATION
    if any(isinstance(item, GarminInvalidSessionError) for item in chain):
        return GarminLoginIssue.INVALID_SESSION
    if any(isinstance(item, GarminMfaError) for item in chain):
        return GarminLoginIssue.MFA
    if any(isinstance(item, GarminRateLimitError) for item in chain) or status == 429:
        return GarminLoginIssue.RATE_LIMIT
    if any(isinstance(item, GarminChallengeError) for item in chain):
        return GarminLoginIssue.CHALLENGE
    if status in {403, 503} and any(
        marker in text
        for marker in ("cloudflare", "captcha", "challenge", "bot", "access denied")
    ):
        return GarminLoginIssue.CHALLENGE
    if any(marker in text for marker in ("mfa", "two-factor", "2fa", "verification code")):
        return GarminLoginIssue.MFA
    if any(isinstance(item, GarminAuthenticationError) for item in chain) or status == 401:
        return GarminLoginIssue.CREDENTIALS
    if any(isinstance(item, (GarminNetworkError, GarminConnectionError)) for item in chain):
        return GarminLoginIssue.NETWORK
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return GarminLoginIssue.INTEGRATION
    return GarminLoginIssue.UNKNOWN


def diagnose_login_error(error: BaseException) -> GarminLoginDiagnostic:
    issue = classify_login_issue(error)
    title, message, action = _COPY[issue]
    return GarminLoginDiagnostic(
        issue=issue,
        title=title,
        message=message,
        action=action,
        exception_type=type(error).__name__,
        http_status=extract_http_status(error),
        garminconnect_version=garminconnect_package_version(),
    )
