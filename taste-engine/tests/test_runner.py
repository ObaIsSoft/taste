import subprocess
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace

from taste_engine.capture import runner, store
from taste_engine.schemas import CaptureRecord, CaptureStatus, Cohort, SiteEntry, Variant
from taste_engine.settings import Settings

OK, FAILED = CaptureStatus.OK, CaptureStatus.FAILED
ENTRIES = [SiteEntry(id=i, url=f"https://s{i}.test/", cohort=Cohort.AWARD) for i in (1, 2, 3)]


CURRENT = Settings().capture_version


def _record(job, status, version=CURRENT):
    return CaptureRecord(
        capture_id=job.capture_id,
        site_id=job.entry.id,
        variant=job.variant,
        requested_url=str(job.entry.url),
        status=status,
        capture_version=version,
        captured_at=datetime.now(UTC),
        duration_s=1.0,
        viewport_width=1440,
        viewport_height=900,
    )


def test_plan_skips_finished_captures_of_this_version_only(fast_settings):
    jobs = runner.plan(ENTRIES, [Variant.ORIGINAL], fast_settings)
    for job, status, version in zip(
        jobs, (OK, FAILED, OK), (CURRENT, CURRENT, "0.0.0"), strict=True
    ):
        store.write_record(_record(job, status, version), fast_settings.capture_dir(job.capture_id))

    assert [j.entry.id for j in runner.plan(ENTRIES, [Variant.ORIGINAL], fast_settings)] == [2, 3]
    assert len(runner.plan(ENTRIES, [Variant.ORIGINAL], fast_settings, force=True)) == 3


def test_failures_are_retried_then_counted(fast_settings, monkeypatch):
    fast_settings.capture.retry_backoff_s = 0
    outcomes = {1: [FAILED, OK], 2: [FAILED, FAILED], 3: [OK]}
    calls = []

    def run_once(job, _settings):
        calls.append(job.entry.id)
        return _record(job, outcomes[job.entry.id].pop(0))

    monkeypatch.setattr(runner, "_run_once", run_once)
    counts = runner.run(runner.plan(ENTRIES, [Variant.ORIGINAL], fast_settings), fast_settings)

    assert counts == Counter(ok=2, failed=1)
    assert sorted(calls) == [1, 1, 2, 2, 3]  # two attempts each, and no third


def test_a_worker_that_dies_or_hangs_is_recorded_as_failed(fast_settings, monkeypatch):
    job = runner.Job(ENTRIES[0], Variant.ORIGINAL)
    died = SimpleNamespace(stderr="Traceback\n  ...\nKilled")
    monkeypatch.setattr(runner.subprocess, "run", lambda *_a, **_k: died)
    record = runner._run_once(job, fast_settings)
    assert record.status == FAILED and "Killed" in record.error

    def hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("capture-one", 300)

    monkeypatch.setattr(runner.subprocess, "run", hang)
    assert "timed out" in runner._run_once(job, fast_settings).error
    assert store.read_record(fast_settings.capture_dir(job.capture_id)).status == FAILED
