"""Reading and writing capture folders. Every write is atomic."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from taste_engine.schemas import CaptureRecord

RECORD_FILE = "capture.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8"
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def write_record(record: CaptureRecord, directory: Path) -> None:
    write_json(directory / RECORD_FILE, record.model_dump(mode="json"))


def read_record(directory: Path) -> CaptureRecord | None:
    path = directory / RECORD_FILE
    if not path.exists():
        return None
    return CaptureRecord.model_validate_json(path.read_text(encoding="utf-8"))


def clear_record(directory: Path) -> None:
    (directory / RECORD_FILE).unlink(missing_ok=True)


def reset_directory(directory: Path) -> None:
    """Start a capture from an empty folder so no stale artifact survives a re-run."""
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
