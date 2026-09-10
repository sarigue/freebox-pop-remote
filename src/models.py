"""Small data models used by the UI and discovery backend."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """Android TV device discovered through mDNS."""

    name: str
    host: str
    model: str = ""
    port: int = 6466

    @property
    def label(self) -> str:
        """Human-readable label for combo boxes."""
        model = f" — {self.model}" if self.model else ""
        return f"{self.name}{model} ({self.host})"
