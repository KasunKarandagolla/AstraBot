"""Path guards for disposable, fixture-only C06 SQLite stores."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".astrabot-c06-synthetic"
KNOWN_FILES = {
    MARKER, "c06_state.sqlite", "owner.sqlite", "venue.sqlite",
    "c06_state.sqlite-journal", "owner.sqlite-journal", "venue.sqlite-journal",
    "c06_state.sqlite-wal", "owner.sqlite-wal", "venue.sqlite-wal",
    "c06_state.sqlite-shm", "owner.sqlite-shm", "venue.sqlite-shm",
}


def prepare_synthetic_state_dir(value: str | Path) -> Path:
    """Create/validate an isolated synthetic directory without reusing data."""
    path = Path(value).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("C06 fixture state must be outside the repository")
    if path == path.parent:
        raise ValueError("filesystem root cannot be a C06 fixture directory")
    if path.exists() and not path.is_dir():
        raise ValueError("C06 fixture state path must be a directory")
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER
    if marker.exists():
        if marker.read_text(encoding="utf-8") != "SYNTHETIC_ONLY\n":
            raise ValueError("C06 fixture directory marker is invalid")
    else:
        unexpected = sorted(item.name for item in path.iterdir() if item.name not in KNOWN_FILES)
        if unexpected or any((path / name).exists() for name in KNOWN_FILES - {MARKER}):
            raise ValueError("refusing to reuse a nonempty directory without the C06 fixture marker")
        marker.write_text("SYNTHETIC_ONLY\n", encoding="utf-8")
    unexpected = sorted(item.name for item in path.iterdir() if item.name not in KNOWN_FILES)
    if unexpected:
        raise ValueError("C06 fixture directory contains unrelated files")
    return path


def reset_synthetic_state_dir(value: str | Path) -> Path:
    """Delete only known SQLite files in an already marked fixture directory."""
    path = Path(value).expanduser().resolve()
    if path == ROOT or ROOT in path.parents or path == path.parent:
        raise ValueError("refusing to reset a repository, filesystem root or unsafe fixture path")
    marker = path / MARKER
    if not path.is_dir() or not marker.is_file() or marker.read_text(encoding="utf-8") != "SYNTHETIC_ONLY\n":
        raise ValueError("reset requires an existing marked synthetic-only directory")
    unexpected = sorted(item.name for item in path.iterdir() if item.name not in KNOWN_FILES)
    if unexpected:
        raise ValueError("refusing to reset a fixture directory containing unrelated files")
    for name in KNOWN_FILES - {MARKER}:
        target = path / name
        if target.is_file():
            target.unlink()
    return path
