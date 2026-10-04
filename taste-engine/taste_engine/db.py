"""Supabase access for the pipeline: publish captures, calibration sets, voters, vote export.

Uses the service key, which bypasses row-level security; it never leaves this
machine or the voting API's server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from collections.abc import Callable
from functools import partial
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError

from supabase import Client, ClientOptions, create_client
from taste_engine import manifest
from taste_engine.analysis.features import FEATURES_FILE
from taste_engine.capture import store
from taste_engine.describe import DESCRIPTION_FILE, is_clean
from taste_engine.schemas import CaptureRecord, CaptureStatus, Variant
from taste_engine.settings import Settings

log = logging.getLogger(__name__)

CONTENT_TYPES = {".jpg": "image/jpeg", ".mp4": "video/mp4"}
PAGE_ROWS = 1000  # the REST API's default row limit per request


def connect(settings: Settings) -> Client:
    if not settings.supabase_url or settings.supabase_service_key is None:
        raise RuntimeError("set SUPABASE_URL and SUPABASE_SERVICE_KEY in taste-engine/.env")
    return create_client(
        settings.supabase_url,
        settings.supabase_service_key.get_secret_value(),
        options=ClientOptions(
            postgrest_client_timeout=settings.request_timeout_s,
            storage_client_timeout=settings.request_timeout_s,
        ),
    )


def _transient(error: Exception) -> bool:
    """A failure of the network or the server, not of the request: worth trying again."""
    if isinstance(error, httpx.TransportError):
        return True  # a dropped, refused or stalled connection
    if isinstance(error, json.JSONDecodeError):
        return True  # the storage client reading an edge error page (a 5xx) that is not JSON
    if isinstance(error, StorageApiError):
        return str(error.status).startswith("5")
    if isinstance(error, APIError):
        return str(error.code).startswith("5") and len(str(error.code)) == 3  # HTTP, not SQL
    return False


def _retry[T](settings: Settings, what: str, call: Callable[[], T]) -> T:
    """Run an idempotent request, retrying transient failures and waiting longer each time."""
    for attempt in range(1, settings.request_attempts + 1):
        try:
            return call()
        except Exception as error:
            if attempt == settings.request_attempts or not _transient(error):
                raise
            log.warning("%s failed (%s: %s); retrying", what, type(error).__name__, error)
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def ensure_bucket(db: Client, settings: Settings) -> None:
    if settings.storage_bucket not in {bucket.id for bucket in db.storage.list_buckets()}:
        db.storage.create_bucket(settings.storage_bucket, options={"public": False})


def media_fingerprint(directory: Path, names: list[str]) -> tuple[str, dict[str, str]]:
    """What a capture shows, as one id: a hash over its files' hashes, in order. New media gets
    a new id, and with it new storage paths, so nothing a voter has seen is ever overwritten.
    Returns the id and each file's sha256."""
    digests = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}
    whole = hashlib.sha256("".join(f"{n}:{d}\n" for n, d in digests.items()).encode())
    return whole.hexdigest()[:16], digests


def _upload(db: Client, settings: Settings, directory: Path, name: str, prefix: str) -> str:
    """Upload one file under its media id. A path is never overwritten: if it exists, it holds
    these same bytes, because the media id is a hash of them."""
    path = f"{prefix}/{name}"
    data = (directory / name).read_bytes()
    upload = partial(
        db.storage.from_(settings.storage_bucket).upload,
        path,
        data,
        {"content-type": CONTENT_TYPES[Path(name).suffix], "upsert": "false"},
    )
    try:
        _retry(settings, f"upload of {path}", upload)
    except StorageApiError as error:
        if str(error.status) != "409" and "exists" not in str(error.message).lower():
            raise
    return path


def _publish_media(
    db: Client, settings: Settings, directory: Path, record: CaptureRecord
) -> tuple[str, list[str], str | None]:
    """Publish the capture's media as a version of its own, unless that version is already
    there. Returns its media id and storage paths. Versions are kept for good: votes point at
    them."""
    names = [still.file for still in record.stills]
    names += [record.reel_file] if record.reel_file else []
    media_id, digests = media_fingerprint(directory, names)
    prefix = f"{record.capture_id}/{media_id}"
    stills = [f"{prefix}/{still.file}" for still in record.stills]
    reel = f"{prefix}/{record.reel_file}" if record.reel_file else None
    known = _retry(
        settings,
        f"media of {record.capture_id}",
        db.table("capture_media")
        .select("media_id")
        .eq("capture_id", record.capture_id)
        .eq("media_id", media_id)
        .execute,
    )
    if known.data:
        return media_id, stills, reel
    for name in names:
        _upload(db, settings, directory, name, prefix)
    version = {
        "capture_id": record.capture_id,
        "media_id": media_id,
        "capture_version": record.capture_version,
        "stills": stills,
        "reel_path": reel,
        "files": {f"{prefix}/{name}": digest for name, digest in digests.items()},
    }
    insert = db.table("capture_media").upsert(
        version, on_conflict="capture_id,media_id", ignore_duplicates=True
    )
    _retry(settings, f"media of {record.capture_id}", insert.execute)
    return media_id, stills, reel


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


def votable(
    record: CaptureRecord | None, description: dict[str, Any] | None, settings: Settings
) -> bool:
    """Only originals that passed QA, and that Claude saw as a live, uncovered page, go online.
    Twins are labelled without votes and stay local, and media nobody will see would only use
    up the free storage."""
    return (
        record is not None
        and record.status == CaptureStatus.OK
        and record.variant is Variant.ORIGINAL
        and record.quality.passed
        and (is_clean(description) or not settings.publish_requires_description)
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
        described = _optional_json(directory / DESCRIPTION_FILE) or {}
        if not votable(record, described.get("description"), settings):
            continue
        entry = entries[record.site_id]
        if record.requested_url != str(entry.url):  # a site id always means the same URL
            raise ValueError(
                f"{record.capture_id} captured {record.requested_url}, "
                f"but site {entry.id} is {entry.url}"
            )
        site = {
            "id": entry.id,
            "url": str(entry.url),
            "cohort": entry.cohort.value,
            "category": entry.category,
        }
        _retry(settings, f"site {entry.id}", db.table("sites").upsert(site).execute)
        existing = _retry(
            settings,
            f"note of {record.capture_id}",
            db.table("captures").select("qa_note").eq("id", record.capture_id).execute,
        )
        reported = bool(existing.data and existing.data[0]["qa_note"])
        # The media first, then the capture switches to it in one step: until then it keeps
        # showing the media it had, which the pairs already served pin.
        media_id, stills, reel = _publish_media(db, settings, directory, record)
        row = capture_row(record, directory, stills, reel, reported) | {"media_id": media_id}
        _retry(settings, record.capture_id, db.table("captures").upsert(row).execute)
        published += 1
        log.info("published %s", record.capture_id)
    return published


def add_voter(db: Client, name: str) -> str:
    """Create a voter and return their invite code; share it with them privately."""
    code = secrets.token_urlsafe(9)
    db.table("voters").insert({"name": name, "invite_code": code}).execute()
    return code


def exclude_capture(db: Client, capture_id: str, reason: str) -> bool:
    """Take a capture out of the voting pool for good: its qa_note keeps it out on re-publish.
    Votes already cast on it stay. Returns whether the capture exists."""
    rows = (
        db.table("captures")
        .update({"in_pool": False, "qa_note": reason})
        .eq("id", capture_id)
        .execute()
        .data
    )
    return bool(rows)


def pool_ids(db: Client) -> set[str]:
    """Captures voters may be served: published, and never taken out of the pool."""
    ids: list[str] = []
    while True:
        page = (
            db.table("captures")
            .select("id")
            .eq("in_pool", True)
            .order("id")
            .range(len(ids), len(ids) + PAGE_ROWS - 1)
            .execute()
            .data
        )
        ids.extend(row["id"] for row in page)
        if len(page) < PAGE_ROWS:
            return set(ids)


def disable_voter(db: Client, name: str) -> int:
    """Switch a voter off: their invite code stops working, their votes stay. Returns how many."""
    return len(db.table("voters").update({"active": False}).eq("name", name).execute().data)


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
    opened): motion reasons are only trusted when the reels were watched. With them, what the
    votes point at, so the export stands on its own: each media version a vote pins (its files
    and their hashes) and each site's URL."""
    rows = select_all(db, "votes", ("id",))
    _write_jsonl(rows, path)
    _write_jsonl(select_all(db, "vote_events", ("id",)), path.with_name("vote_events.jsonl"))
    media = select_all(db, "capture_media", ("capture_id", "media_id"))
    _write_jsonl(media, path.with_name("capture_media.jsonl"))
    _write_jsonl(select_all(db, "sites", ("id",)), path.with_name("sites.jsonl"))
    return len(rows)
