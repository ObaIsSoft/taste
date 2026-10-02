import pytest

from taste_engine.capture import degrade, js
from taste_engine.capture.overlays import same_site
from taste_engine.capture.quality import assess
from taste_engine.cli import parse_ids
from taste_engine.schemas import Variant
from taste_engine.settings import CaptureSettings

CFG = CaptureSettings()


def _assess(**overrides):
    values = {
        "cfg": CFG,
        "requested_url": "https://studio.example.com/",
        "final_url": "https://studio.example.com/",
        "http_status": 200,
        "title": "Studio",
        "text_sample": "x" * 5000,
        "hero_spread": 40.0,
        "consent_left": [],
        "reel_ok": True,
    }
    values.update(overrides)
    return assess(**values)


def test_clean_capture_passes():
    assert _assess().passed


@pytest.mark.parametrize(
    ("overrides", "flag"),
    [
        ({"hero_spread": 1.0}, "blank_hero"),
        ({"http_status": 403}, "bot_block"),
        ({"text_sample": "Automated access not allowed"}, "bot_block"),
        ({"http_status": 404}, "not_found"),
        ({"title": "Page not found"}, "not_found"),
        ({"final_url": "https://www.google.com/"}, "navigated_away"),
        ({"consent_left": ['[role="dialog"]']}, "overlay_remaining"),
        ({"reel_ok": False}, "reel_missing"),
    ],
)
def test_each_problem_fails_qa(overrides, flag):
    flags = _assess(**overrides)
    assert getattr(flags, flag)
    assert not flags.passed


def test_long_pages_are_not_flagged_by_words_in_their_copy():
    copy = "We help brands avoid the 404 of the soul. " * 200
    assert _assess(text_sample=copy).passed


@pytest.mark.parametrize(
    ("url", "origin", "expected"),
    [
        ("https://www.example.com/a", "https://example.com/", True),
        ("https://shop.example.com/", "https://example.com/", True),
        ("https://www.google.com/", "https://example.com/", False),
    ],
)
def test_same_site(url, origin, expected):
    assert same_site(url, origin) is expected


def test_init_script_is_invoked_not_just_defined():
    script = js.init_script(10, 1.0).strip()
    assert script.startswith("(() =>") and script.endswith("})();")


def test_every_twin_has_a_profile_and_original_has_none():
    assert degrade.init_script(Variant.ORIGINAL) is None
    for variant in Variant:
        if variant is not Variant.ORIGINAL:
            assert degrade.init_script(variant).strip().endswith("})();")


def test_parse_ids():
    assert parse_ids("1,4, 10-12") == [1, 4, 10, 11, 12]
