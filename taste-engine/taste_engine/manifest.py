"""The site manifest: the one list of sites the engine knows about.

Each row is (id, url, cohort, category, source, notes). Ids are assigned once,
on import, and never derived from a list position again. URLs are normalised
once, which also repairs the slashes that were appended to every URL in
``list.md`` (they broke query strings, fragments and file paths).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from taste_engine.schemas import Cohort, SiteEntry

FIELDS = ("id", "url", "cohort", "category", "source", "notes")
_URL_IN_LINE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_DEFAULT_PORTS = {"http": 80, "https": 443}


class ManifestError(ValueError):
    pass


def normalize_url(raw: str) -> str:
    """Canonical form used for capture and de-duplication.

    Lower-cases scheme and host, drops default ports, removes a trailing slash
    that was appended after a query, fragment or file name, and drops the
    trailing slash of any non-root path.
    """
    url = raw.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        raise ManifestError(f"URL has no valid host: {raw!r}")
    port = parts.port
    netloc = host if port in (None, _DEFAULT_PORTS.get(scheme)) else f"{host}:{port}"

    path, query, fragment = parts.path, parts.query, parts.fragment
    if fragment.endswith("/"):
        fragment = fragment.rstrip("/")
    elif query.endswith("/"):
        query = query.rstrip("/")
    if path not in ("", "/"):
        path = path.rstrip("/")
    if not path:
        path = "/"
    return urlunsplit((scheme, netloc, path, query, fragment))


def urls_from_text(text: str) -> list[str]:
    """First URL on each line, in order, normalised and de-duplicated."""
    seen: set[str] = set()
    urls: list[str] = []
    for line in text.splitlines():
        match = _URL_IN_LINE.search(line)
        if not match:
            continue
        url = normalize_url(match.group(0))
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def entries_from_urls(
    urls: Iterable[str], cohort: Cohort, source: str, first_id: int = 1
) -> list[SiteEntry]:
    return [
        SiteEntry(id=first_id + i, url=url, cohort=cohort, source=source)
        for i, url in enumerate(urls)
    ]


def validate(entries: list[SiteEntry]) -> None:
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise ManifestError("duplicate ids in manifest")
    urls = [str(e.url) for e in entries]
    duplicates = {u for u in urls if urls.count(u) > 1}
    if duplicates:
        raise ManifestError(f"duplicate URLs in manifest: {sorted(duplicates)[:5]}")


def read_manifest(path: Path) -> list[SiteEntry]:
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    entries = [
        SiteEntry(
            id=int(row["id"]),
            url=row["url"],
            cohort=Cohort(row["cohort"]),
            category=row.get("category") or None,
            source=row.get("source") or None,
            notes=row.get("notes") or None,
        )
        for row in rows
    ]
    validate(entries)
    return entries


def write_manifest(entries: list[SiteEntry], path: Path) -> None:
    validate(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for entry in sorted(entries, key=lambda e: e.id):
            row = entry.model_dump(mode="json")
            writer.writerow({field: "" if row[field] is None else row[field] for field in FIELDS})


def append_urls(path: Path, urls: Iterable[str], cohort: Cohort, source: str) -> list[SiteEntry]:
    """Add new URLs to an existing manifest with fresh ids; existing URLs are skipped."""
    entries = read_manifest(path)
    known = {str(e.url) for e in entries}
    fresh = [u for u in (normalize_url(u) for u in urls) if u not in known]
    next_id = max((e.id for e in entries), default=0) + 1
    added = entries_from_urls(fresh, cohort, source, first_id=next_id)
    write_manifest(entries + added, path)
    return added


def select(
    entries: list[SiteEntry],
    ids: Iterable[int] | None = None,
    cohort: Cohort | None = None,
    limit: int | None = None,
) -> list[SiteEntry]:
    wanted = set(ids) if ids else None
    chosen = [
        e
        for e in entries
        if (wanted is None or e.id in wanted) and (cohort is None or e.cohort == cohort)
    ]
    if wanted:
        missing = wanted - {e.id for e in chosen}
        if missing:
            raise ManifestError(f"ids not in manifest: {sorted(missing)}")
    return chosen[:limit] if limit else chosen
