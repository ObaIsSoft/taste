"""Supabase access for the pipeline: publish captures, calibration sets, voters, vote export.

Uses the service key, which bypasses row-level security; it never leaves this
machine or the voting API's server.
"""

from __future__ import annotations

import json
import logging
import secrets
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.parse import quote

from supabase import Client, create_client
from taste_engine import manifest
from taste_engine.analysis.features import FEATURES_FILE
from taste_engine.capture import store
from taste_engine.describe import DESCRIPTION_FILE
from taste_engine.schemas import CaptureRecord, CaptureStatus, Variant
from taste_engine.settings import Settings

log = logging.getLogger(__name__)

CONTENT_TYPES = {".jpg": "image/jpeg", ".mp4": "video/mp4"}
PAGE_ROWS = 1000  # the REST API's default row limit per request


def connect(settings: Settings) -> Client:
    if not settings.supabase_url or settings.supabase_service_key is None:
        raise RuntimeError("set SUPABASE_URL and SUPABASE_SERVICE_KEY in taste-engine/.env")
    return create_client(settings.supabase_url, settings.supabase_service_key.get_secret_value())


def ensure_bucket(db: Client, settings: Settings) -> None:
    if settings.storage_bucket not in {bucket.id for bucket in db.storage.list_buckets()}:
        db.storage.create_bucket(settings.storage_bucket, options={"public": False})


def _upload(db: Client, settings: Settings, directory: Path, name: str) -> str:
    path = f"{directory.name}/{name}"
    db.storage.from_(settings.storage_bucket).upload(
        path,
        (directory / name).read_bytes(),
        {"content-type": CONTENT_TYPES[Path(name).suffix], "upsert": "true"},
    )
    return path


def _optional_json(path: Path) -> Any | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def capture_row(
    record: CaptureRecord, directory: Path, stills: list[str], reel: str | None, reported: bool
) -> dict[str, Any]:
    return {
        "id": record.capture_id,
        "site_id": record.site_id,
        "variant": record.variant.value,
        "capture_version": record.capture_version,
        "qa_passed": record.quality.passed,
        "stills": stills,
        "reel_path": reel,
        "final_url": record.final_url,
        "features": _optional_json(directory / FEATURES_FILE),
        "description": _optional_json(directory / DESCRIPTION_FILE),
        # twins are labelled without votes; a voter's broken report keeps a capture out
        "in_pool": record.quality.passed and record.variant is Variant.ORIGINAL and not reported,
    }


def votable(record: CaptureRecord | None) -> bool:
    """Only originals that passed QA go online: twins are labelled without votes and stay local,
    and media nobody will see would only use up the free storage."""
    return (
        record is not None
        and record.status == CaptureStatus.OK
        and record.variant is Variant.ORIGINAL
        and record.quality.passed
    )


def publish(settings: Settings, db: Client, capture_ids: list[str] | None = None) -> int:
    """Upload media and upsert site and capture rows for votable captures. Returns the count."""
    ensure_bucket(db, settings)
    entries = {entry.id: entry for entry in manifest.read_manifest(settings.manifest_path)}
    published = 0
    for directory in sorted(p for p in settings.captures_dir.glob("*") if p.is_dir()):
        if capture_ids is not None and directory.name not in capture_ids:
            continue
        record = store.read_record(directory)
        if not votable(record):
            continue
        entry = entries[record.site_id]
        db.table("sites").upsert(
            {
                "id": entry.id,
                "url": str(entry.url),
                "cohort": entry.cohort.value,
                "category": entry.category,
            }
        ).execute()
        stills = [_upload(db, settings, directory, still.file) for still in record.stills]
        reel = _upload(db, settings, directory, record.reel_file) if record.reel_file else None
        existing = db.table("captures").select("qa_note").eq("id", record.capture_id).execute()
        reported = bool(existing.data and existing.data[0]["qa_note"])
        db.table("captures").upsert(
            capture_row(record, directory, stills, reel, reported)
        ).execute()
        published += 1
        log.info("published %s", record.capture_id)
    return published


def add_voter(db: Client, name: str) -> str:
    """Create a voter and return their invite code; share it with them privately."""
    code = secrets.token_urlsafe(9)
    db.table("voters").insert({"name": name, "invite_code": code}).execute()
    return code


def list_voters(db: Client) -> list[dict[str, Any]]:
    """Every voter, oldest first, with their invite code: for re-sending a lost link."""
    return (
        db.table("voters")
        .select("name,invite_code,active,created_at")
        .order("created_at")
        .execute()
        .data
    )


def invite_link(voting_url: str, code: str) -> str:
    """A link that signs the voter in. The code is in the fragment, so no server ever logs it."""
    return f"{voting_url.rstrip('/')}/#invite={quote(code, safe='')}"


def calibration_rows(capture_ids: list[str], round_kind: str) -> list[dict[str, str]]:
    return [
        {"round": round_kind, "capture_a": a, "capture_b": b}
        for a, b in combinations(sorted(set(capture_ids)), 2)
    ]


def create_calibration(db: Client, round_kind: str, capture_ids: list[str]) -> int:
    rows = calibration_rows(capture_ids, round_kind)
    db.table("calibration_pairs").upsert(
        rows, on_conflict="round,capture_a,capture_b", ignore_duplicates=True
    ).execute()
    return len(rows)


def select_all(db: Client, table: str, order: tuple[str, ...]) -> list[dict[str, Any]]:
    """Every row of a table or view, a page at a time, in an order that keeps pages stable."""
    rows: list[dict[str, Any]] = []
    while True:
        query = db.table(table).select("*")
        for column in order:
            query = query.order(column)
        page = query.range(len(rows), len(rows) + PAGE_ROWS - 1).execute().data
        rows.extend(page)
        if len(page) < PAGE_ROWS:
            return rows


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)


def export_votes(db: Client, path: Path) -> int:
    """Every vote, and next to it every vote event (which reels were played, which live sites
    opened): motion reasons are only trusted when the reels were watched."""
    rows = select_all(db, "votes", ("id",))
    _write_jsonl(rows, path)
    _write_jsonl(select_all(db, "vote_events", ("id",)), path.with_name("vote_events.jsonl"))
    return len(rows)
