"""Claude Message Batches: submit requests in size-limited chunks, then collect the results.

Shared by every batch job (descriptions, page generation). Open batch ids are
kept in data/state/<job>_batches.json, so results can be collected later, even
by another process. Batches cost half the standard price.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anthropic

from taste_engine.capture import store
from taste_engine.settings import Settings

log = logging.getLogger(__name__)


def chunk_requests(requests: list[dict[str, Any]], max_bytes: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for request in requests:
        request_size = len(json.dumps(request))
        if current and size + request_size > max_bytes:
            chunks.append(current)
            current, size = [], 0
        current.append(request)
        size += request_size
    if current:
        chunks.append(current)
    return chunks


def _state(settings: Settings, job: str) -> Path:
    return settings.state_dir / f"{job}_batches.json"


def open_batches(settings: Settings, job: str) -> list[str]:
    path = _state(settings, job)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def submit(
    settings: Settings, client: anthropic.Anthropic, job: str, requests: list[dict[str, Any]]
) -> list[str]:
    batch_ids = []
    for chunk in chunk_requests(requests, settings.claude.batch_max_bytes):
        batch = client.messages.batches.create(requests=chunk)
        batch_ids.append(batch.id)
        log.info("%s: submitted batch %s with %d requests", job, batch.id, len(chunk))
    store.write_json(_state(settings, job), open_batches(settings, job) + batch_ids)
    return batch_ids


def collect(
    settings: Settings, client: anthropic.Anthropic, job: str, wait: bool = True
) -> Iterator[tuple[str, Any]]:
    """Yield (batch_id, result) for every request of every finished batch.

    A batch is closed only once all its results have been handled, so a crash
    part-way leaves it open and the next run collects it again. Batches still
    processing stay open when wait is False.
    """
    for batch_id in open_batches(settings, job):
        batch = client.messages.batches.retrieve(batch_id)
        while wait and batch.processing_status != "ended":
            time.sleep(settings.claude.batch_poll_s)
            batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            continue
        for result in client.messages.batches.results(batch_id):
            yield batch_id, result
        remaining = [b for b in open_batches(settings, job) if b != batch_id]
        store.write_json(_state(settings, job), remaining)


def text_of(result: Any) -> tuple[str | None, str | None]:
    """The reply text, or None and the reason it should be retried."""
    if result.result.type != "succeeded":
        return None, result.result.type
    message = result.result.message
    if message.stop_reason in ("refusal", "max_tokens"):
        return None, message.stop_reason
    text = next((block.text for block in message.content if block.type == "text"), None)
    return (text, None) if text is not None else (None, "no text block")
