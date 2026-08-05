"""Single source of truth for the service release version."""

from pathlib import Path

__version__ = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
