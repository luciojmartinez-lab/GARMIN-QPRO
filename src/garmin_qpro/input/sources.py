"""Load individual FIT files and ZIP containers into immutable memory sources."""

from dataclasses import dataclass, field
from hashlib import sha256 as calculate_sha256
from pathlib import Path


class UnsupportedInputError(ValueError):
    """Raised when an input file is neither FIT nor ZIP."""


@dataclass(frozen=True, slots=True)
class FitSource:
    """Immutable FIT bytes with their source identity and content hash."""

    source_name: str
    container_name: str | None
    member_path: str | None
    data: bytes = field(repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("FitSource data must be bytes")
        object.__setattr__(
            self, "sha256", calculate_sha256(self.data).hexdigest()
        )


def load_fit_sources(path: Path) -> tuple[FitSource, ...]:
    """Load a FIT file or all safe FIT members of a ZIP without extraction."""

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    suffix = input_path.suffix.casefold()
    if suffix == ".fit":
        return (
            FitSource(
                source_name=input_path.name,
                container_name=None,
                member_path=None,
                data=input_path.read_bytes(),
            ),
        )

    if suffix == ".zip":
        from .zip_loader import load_zip_fit_sources

        return load_zip_fit_sources(input_path)

    raise UnsupportedInputError(
        f"Unsupported input extension: {input_path.suffix or '<none>'}"
    )
