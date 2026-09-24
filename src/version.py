"""Canonical Rove toolchain version."""

from pathlib import Path


VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()

if not VERSION:
    raise RuntimeError("Rove VERSION file is empty")
