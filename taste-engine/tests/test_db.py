from datetime import UTC, datetime
from types import SimpleNamespace

from taste_engine import db, manifest
from taste_engine.capture import store
from taste_engine.schemas import CaptureRecord, CaptureStatus, Cohort, QualityFlags, Still, Variant
from taste_engine.settings import Settings


class FakeDB:
    """Records what publish would send to Supabase."""

    def __init__(self, reported=()):
        self.uploads, self.upserts, self.reported = [], [], set(reported)
        self.storage = SimpleNamespace(
            list_buckets=lambda: [], create_bucket=lambda *a, **k: None, from_=lambda _b: self
        )
        self._table = None
        self._filter = None

    def upload(self, path, data, options):
        self.uploads.append((path, options["content-type"]))

    def table(self, name):
        self._table = name
        return self

    def upsert(self, row, **_):
        self.upserts.append((self._table, row))
        return self

    def select(self, *_):
        return self

    def eq(self, _column, value):
        self._filter = value
        return self

    def execute(self):
        note = "reported broken by a voter" if self._filter in self.reported else None
        return SimpleNamespace(data=[{"qa_note": note}] if self._filter else [])


def _capture(settings, site_id, variant=Variant.ORIGINAL, passed=True):
    record = CaptureRecord(
        capture_id=f"{site_id:04d}-{variant.value}",
        site_id=site_id,
        variant=variant,
        requested_url="https://a.test/",
        status=CaptureStatus.OK,
        capture_version="2.0.0",
        captured_at=datetime.now(UTC),
        duration_s=1.0,
        viewport_width=1440,
        viewport_height=900,
        stills=[Still(index=1, file="screen-1.jpg", scroll_y=0, method="top")],
        reel_file="reel.mp4",
        quality=QualityFlags(blank_hero=not passed),
    )
    directory = settings.capture_dir(record.capture_id)
    directory.mkdir(parents=True)
    (directory / "screen-1.jpg").write_bytes(b"jpg")
    (directory / "reel.mp4").write_bytes(b"mp4")
    store.write_record(record, directory)


def test_publish_uploads_media_and_only_pools_clean_originals(tmp_path):
    settings = Settings(data_dir=tmp_path, manifest_path=tmp_path / "sites.csv")
    entries = manifest.entries_from_urls(
        ["https://a.test/", "https://b.test/", "https://c.test/"], Cohort.AWARD, "t"
    )
    manifest.write_manifest(entries, settings.manifest_path)
    _capture(settings, 1)
    _capture(settings, 1, Variant.TYPOGRAPHY)
    _capture(settings, 2, passed=False)
    _capture(settings, 3)
    fake = FakeDB(reported={"0003-original"})

    assert db.publish(settings, fake) == 4
    pooled = {row["id"]: row["in_pool"] for table, row in fake.upserts if table == "captures"}
    assert pooled == {
        "0001-original": True,
        "0001-typography": False,  # twins are labelled without votes
        "0002-original": False,  # failed QA
        "0003-original": False,  # a voter reported it broken
    }
    assert ("0001-original/reel.mp4", "video/mp4") in fake.uploads


def test_fourteen_sites_make_ninety_one_calibration_pairs():
    ids = [f"{i:04d}-original" for i in range(1, 15)]
    rows = db.calibration_rows(ids + ids[:2], "visual")
    assert len(rows) == 91
    assert all(row["capture_a"] < row["capture_b"] for row in rows)
