from datetime import UTC, datetime
from types import SimpleNamespace

from fakes import FakeSupabase
from storage3.exceptions import StorageApiError

from taste_engine import db, manifest
from taste_engine.capture import store
from taste_engine.schemas import CaptureRecord, CaptureStatus, Cohort, QualityFlags, Still, Variant
from taste_engine.settings import Settings

KEYS = {"sites": ("id",), "captures": ("id",), "capture_media": ("capture_id", "media_id")}


class FakeDB:
    """What publish touches, in memory: tables, and a bucket that, like the real one, refuses to
    overwrite a file."""

    def __init__(self, reported=()):
        self.files, self.uploads = {}, []
        self.rows = {name: {} for name in KEYS}
        for capture_id in reported:
            self.rows["captures"][(capture_id,)] = {
                "id": capture_id,
                "qa_note": "reported broken by a voter",
            }
        self.storage = SimpleNamespace(
            list_buckets=lambda: [], create_bucket=lambda *a, **k: None, from_=lambda _b: self
        )

    def upload(self, path, data, options):
        if path in self.files:
            raise StorageApiError("The resource already exists", "Duplicate", 409)
        self.files[path] = data
        self.uploads.append((path, options["content-type"]))

    def table(self, name):
        return _Table(self, name)

    def row(self, name, *key):
        return self.rows[name].get(key)


class _Table:
    def __init__(self, fake, name):
        self.fake, self.name, self.filters, self.action = fake, name, [], ("select", "*")

    def select(self, columns="*"):
        self.action = ("select", columns)
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def upsert(self, row, ignore_duplicates=False, **_):
        self.action = ("upsert", row, ignore_duplicates)
        return self

    def execute(self):
        table = self.fake.rows[self.name]
        if self.action[0] == "upsert":
            _, row, ignore = self.action
            key = tuple(row[k] for k in KEYS[self.name])
            if not (key in table and ignore):
                table[key] = {**table.get(key, {}), **row}
            return SimpleNamespace(data=[table[key]])
        found = [r for r in table.values() if all(r.get(c) == v for c, v in self.filters)]
        columns = self.action[1]
        if columns != "*":  # like the database: every selected column, null when never set
            found = [{c: r.get(c) for c in columns.split(",")} for r in found]
        return SimpleNamespace(data=found)


CLEAN = {"obstruction": "none", "page_state": "live_site"}


def _capture(settings, site_id, variant=Variant.ORIGINAL, passed=True, description=CLEAN):
    record = CaptureRecord(
        capture_id=f"{site_id:04d}-{variant.value}",
        site_id=site_id,
        variant=variant,
        requested_url=f"https://{'abcde'[site_id - 1]}.test/",
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
    if description is not None:
        store.write_json(directory / "description.json", {"description": description})
    return directory


def _settings(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        manifest_path=tmp_path / "sites.csv",
        publish_requires_description=True,  # whatever the local .env says
    )
    entries = manifest.entries_from_urls([f"https://{c}.test/" for c in "abcde"], Cohort.AWARD, "t")
    manifest.write_manifest(entries, settings.manifest_path)
    return settings


def test_publish_puts_only_votable_originals_online(tmp_path):
    settings = _settings(tmp_path)
    _capture(settings, 1)
    _capture(settings, 1, Variant.TYPOGRAPHY)
    _capture(settings, 2, passed=False)
    _capture(settings, 3)
    _capture(
        settings,
        4,
        description={"obstruction": "newsletter_or_offer_popup", "page_state": "live_site"},
    )
    _capture(settings, 5, description=None)  # Claude has not checked it yet
    fake = FakeDB(reported={"0003-original"})

    assert db.publish(settings, fake) == 2  # the twin, the QA failure and 4 and 5 stay local
    pooled = {key[0]: row["in_pool"] for key, row in fake.rows["captures"].items()}
    assert pooled == {
        "0001-original": True,
        "0003-original": False,  # a voter reported it broken: published, but not served
    }
    assert fake.row("sites", 1)["url"] == "https://a.test/"
    assert not [path for path, _ in fake.uploads if path.startswith(("0001-typography", "0002"))]


def test_media_is_published_as_a_version_and_never_overwritten(tmp_path):
    settings = _settings(tmp_path)
    directory = _capture(settings, 1)
    fake = FakeDB()

    db.publish(settings, fake)
    first = fake.row("captures", "0001-original")["media_id"]
    version = fake.row("capture_media", "0001-original", first)
    assert version["stills"] == [f"0001-original/{first}/screen-1.jpg"]
    assert version["reel_path"] == f"0001-original/{first}/reel.mp4"
    assert set(version["files"]) == {*version["stills"], version["reel_path"]}
    assert fake.row("captures", "0001-original")["stills"] == version["stills"]

    db.publish(settings, fake)  # nothing changed: nothing uploaded, no new version
    assert len(fake.uploads) == 2 and len(fake.rows["capture_media"]) == 1

    (directory / "screen-1.jpg").write_bytes(b"a new capture of the hero")
    db.publish(settings, fake)  # new media: a new version beside the old one
    second = fake.row("captures", "0001-original")["media_id"]
    assert second != first and len(fake.rows["capture_media"]) == 2
    assert fake.files[f"0001-original/{first}/screen-1.jpg"] == b"jpg"  # what voters saw stays
    assert fake.files[f"0001-original/{second}/screen-1.jpg"] == b"a new capture of the hero"


def test_a_capture_of_another_url_is_never_published_as_this_site(tmp_path):
    settings = _settings(tmp_path)
    directory = _capture(settings, 1)
    record = store.read_record(directory)
    store.write_record(
        record.model_copy(update={"requested_url": "https://other.test/"}), directory
    )
    try:
        db.publish(settings, FakeDB())
    except ValueError as error:
        assert "site 1 is https://a.test/" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_fourteen_sites_make_ninety_one_calibration_pairs():
    ids = [f"{i:04d}-original" for i in range(1, 15)]
    rows = db.calibration_rows(ids + ids[:2], "visual")
    assert len(rows) == 91
    assert all(row["capture_a"] < row["capture_b"] for row in rows)


def test_the_live_pool_leaves_out_unpublished_and_excluded_captures():
    client = FakeSupabase()
    client.tables["captures"] = [
        {"id": "0001-original", "in_pool": True},
        {"id": "0002-original", "in_pool": False},  # excluded after publishing
    ]
    assert db.pool_ids(client) == {"0001-original"}


def test_transient_failures_are_retried_and_real_errors_are_not(monkeypatch):
    import httpx
    from postgrest.exceptions import APIError
    from storage3.exceptions import StorageApiError

    monkeypatch.setattr(db.time, "sleep", lambda _s: None)
    settings = Settings(request_attempts=3)
    failures = [httpx.RemoteProtocolError("Server disconnected"), StorageApiError("x", "y", 520)]

    def flaky():
        if failures:
            raise failures.pop(0)
        return "done"

    assert db._retry(settings, "upload", flaky) == "done"

    calls = []

    def bad_request():
        calls.append(1)
        raise APIError({"message": "bad", "code": "23505"})  # a SQL error: retrying cannot help

    try:
        db._retry(settings, "row", bad_request)
    except APIError:
        assert calls == [1]
    else:
        raise AssertionError("expected the error")

    def always_down():
        calls.append(1)
        raise httpx.ReadTimeout("stalled")

    calls.clear()
    try:
        db._retry(settings, "upload", always_down)
    except httpx.ReadTimeout:
        assert len(calls) == 3  # gives up after request_attempts
    else:
        raise AssertionError("expected the error")


class _Voters:
    def __init__(self):
        self.rows = []

    def table(self, _name):
        return self

    def insert(self, row):
        self.rows.append(row)
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_each_voter_gets_a_fresh_code_and_a_link_that_keeps_it_out_of_server_logs():
    voters = _Voters()
    first, second = db.add_voter(voters, "Ada"), db.add_voter(voters, "Grace")
    assert first != second and len(first) >= 12
    assert voters.rows[0] == {"name": "Ada", "invite_code": first}

    link = db.invite_link("https://votes.test/", first)
    assert link == f"https://votes.test/#invite={first}"
    assert db.invite_link("https://votes.test", "a/b c") == "https://votes.test/#invite=a%2Fb%20c"
