"""Batch capture: one subprocess per capture, retries, and resumable state.

Each capture runs in its own Python process, so a browser crash, a hung page or
a leak can never take the batch down. Finished captures are skipped on the next
run unless the capture version changed or --force is given.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from taste_engine.capture import store
from taste_engine.schemas import CaptureRecord, CaptureStatus, SiteEntry, Variant, capture_id
from taste_engine.settings import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    entry: SiteEntry
    variant: Variant

    @property
    def capture_id(self) -> str:
        return capture_id(self.entry.id, self.variant)


def plan(
    entries: list[SiteEntry], variants: list[Variant], settings: Settings, force: bool = False
) -> list[Job]:
    jobs = []
    for entry in entries:
        for variant in variants:
            job = Job(entry, variant)
            existing = store.read_record(settings.capture_dir(job.capture_id))
            done = (
                existing is not None
                and existing.status == CaptureStatus.OK
                and existing.capture_version == settings.capture_version
            )
            if force or not done:
                jobs.append(job)
    return jobs


def _failed(job: Job, settings: Settings, error: str, started: float) -> CaptureRecord:
    cfg = settings.capture
    record = CaptureRecord(
        capture_id=job.capture_id,
        site_id=job.entry.id,
        variant=job.variant,
        requested_url=str(job.entry.url),
        status=CaptureStatus.FAILED,
        error=error,
        capture_version=settings.capture_version,
        captured_at=datetime.now(UTC),
        duration_s=round(time.monotonic() - started, 1),
        viewport_width=cfg.viewport_width,
        viewport_height=cfg.viewport_height,
    )
    store.write_record(record, settings.capture_dir(job.capture_id))
    return record


def _run_once(job: Job, settings: Settings) -> CaptureRecord:
    command = [
        sys.executable,
        "-m",
        "taste_engine",
        "capture-one",
        "--site-id",
        str(job.entry.id),
        "--variant",
        job.variant.value,
    ]
    directory = settings.capture_dir(job.capture_id)
    store.clear_record(directory)  # a record after the run can only come from this run
    started = time.monotonic()
    timeout = settings.capture.site_timeout_s
    try:
        result = subprocess.run(
            command, timeout=timeout, capture_output=True, text=True, check=False
        )
    except subprocess.TimeoutExpired:
        return _failed(job, settings, f"timed out after {timeout:.0f}s", started)
    record = store.read_record(directory)
    if record is None:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        return _failed(
            job, settings, "worker exited without a record: " + " | ".join(tail), started
        )
    return record


def _with_retries(job: Job, settings: Settings) -> CaptureRecord:
    cfg = settings.capture
    record = _run_once(job, settings)
    for attempt in range(2, cfg.attempts + 1):
        if record.status == CaptureStatus.OK:
            break
        log.warning("%s failed (%s); retry %d", job.capture_id, record.error, attempt)
        time.sleep(cfg.retry_backoff_s * (attempt - 1))
        record = _run_once(job, settings)
    return record


def run(jobs: list[Job], settings: Settings) -> Counter[str]:
    """Run jobs in parallel worker processes. Returns counts of ok, qa_failed and failed."""
    counts: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=settings.capture.workers) as pool:
        futures = {pool.submit(_with_retries, job, settings): job for job in jobs}
        for future in as_completed(futures):
            record = future.result()
            if record.status == CaptureStatus.FAILED:
                counts["failed"] += 1
                log.error("%s failed: %s", record.capture_id, record.error)
            elif not record.quality.passed:
                counts["qa_failed"] += 1
                log.warning("%s captured but failed QA: %s", record.capture_id, record.quality)
            else:
                counts["ok"] += 1
                log.info("%s ok in %.0fs", record.capture_id, record.duration_s)
    return counts
