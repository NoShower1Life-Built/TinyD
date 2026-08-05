from dataclasses import dataclass


@dataclass(frozen=True)
class VCIRSpec:
    """Versioned TinyD execution specification."""

    version: str
    name: str
    actions: tuple[str, ...]
