import pytest

from taste_engine import manifest
from taste_engine.schemas import Cohort


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.ownthepatch.co.uk/", "https://www.ownthepatch.co.uk/"),
        ("HTTPS://Example.COM:443/About/", "https://example.com/About"),
        ("kortrijkxpo.com/en/", "https://kortrijkxpo.com/en"),
        ("https://demo.site/?password=demo/", "https://demo.site/?password=demo"),
        ("https://thewoodetfils.com/propos#notre-monde/", "https://thewoodetfils.com/propos#notre-monde"),
        ("https://gchf.kr/index.html/", "https://gchf.kr/index.html"),
        ("http://example.com:8080/x", "http://example.com:8080/x"),
    ],
)
def test_normalize_url_repairs_list_md_damage(raw, expected):
    assert manifest.normalize_url(raw) == expected


def test_normalize_url_rejects_hostless_input():
    with pytest.raises(manifest.ManifestError):
        manifest.normalize_url("https://localhost/")


def test_urls_from_text_keeps_order_and_drops_duplicates():
    text = """1. https://penti.ai/
2. https://driveberry.fr/

started here for the new batch
3. https://penti.ai
488. https://a-site.com/page/
488. https://b-site.com/
"""
    assert manifest.urls_from_text(text) == [
        "https://penti.ai/",
        "https://driveberry.fr/",
        "https://a-site.com/page",
        "https://b-site.com/",
    ]


def test_roundtrip_append_and_select(tmp_path):
    path = tmp_path / "sites.csv"
    entries = manifest.entries_from_urls(["https://a.com/", "https://b.com/"], Cohort.AWARD, "test")
    manifest.write_manifest(entries, path)

    extra = ["https://b.com", "https://c.com/x/"]
    added = manifest.append_urls(path, extra, Cohort.ORDINARY, "extra")
    assert [(e.id, str(e.url)) for e in added] == [(3, "https://c.com/x")]

    loaded = manifest.read_manifest(path)
    assert [e.id for e in loaded] == [1, 2, 3]
    assert [e.id for e in manifest.select(loaded, cohort=Cohort.AWARD)] == [1, 2]
    assert [e.id for e in manifest.select(loaded, limit=1)] == [1]
    with pytest.raises(manifest.ManifestError):
        manifest.select(loaded, ids=[9])


def test_duplicate_urls_are_rejected(tmp_path):
    entries = manifest.entries_from_urls(["https://a.com/"], Cohort.AWARD, "t")
    entries += manifest.entries_from_urls(["https://a.com/"], Cohort.AWARD, "t", first_id=2)
    with pytest.raises(manifest.ManifestError):
        manifest.write_manifest(entries, tmp_path / "sites.csv")
