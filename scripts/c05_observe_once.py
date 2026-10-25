"""Manually run the bounded C05 public observer (fixtures by default)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.observer import _run_cli


if __name__ == "__main__":
    raise SystemExit(_run_cli())
