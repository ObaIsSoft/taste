"""End-to-end capture against a local fixture site. Needs Playwright browsers and ffmpeg."""

import json
import subprocess

import pytest
from PIL import Image

from taste_engine.capture import reel
from taste_engine.capture.site import TOKENS_FILE, capture_site
from taste_engine.schemas import CaptureStatus, Cohort, SiteEntry, Variant

pytestmark = pytest.mark.browser


def _capture(url, settings, variant=Variant.ORIGINAL):
    return capture_site(SiteEntry(id=1, url=url, cohort=Cohort.AWARD), variant, settings)


def _sibling(fixture_site_url, name):
    return fixture_site_url.rsplit("/", 1)[0] + "/" + name


def _stills_only(settings):
    settings.capture.reel.enabled = False
    settings.capture.reduced_motion_check = False


def test_original_capture(fixture_site_url, fast_settings):
    entry = SiteEntry(id=1, url=fixture_site_url, cohort=Cohort.AWARD)
    record = capture_site(entry, Variant.ORIGINAL, fast_settings)
    folder = fast_settings.capture_dir(record.capture_id)

    assert record.status == CaptureStatus.OK, record.error
    assert record.quality.passed, record.quality
    assert record.http_status == 200
    assert record.overlay_actions[0] == "consent:accept all"
    assert "menu" in record.overlay_actions

    assert [s.index for s in record.stills] == [1, 2, 3, 4]
    assert all((folder / s.file).exists() for s in record.stills)
    assert record.stills[1].method == "native"

    assert record.gsap_call_count >= 3  # the hook really runs: to, timeline, timeline.to
    assert record.libraries["webgl"] and record.libraries["gsap"]
    assert record.animation_count >= 1

    metrics = record.metrics
    assert metrics.content_visible_ms and metrics.content_visible_ms >= 1000  # the preloader wait
    assert metrics.scroll_hijacked is False
    assert metrics.uses_reduced_motion_query is True
    assert metrics.reduced_motion_respected is True
    assert metrics.dropped_frame_ratio is not None
    assert metrics.inline_motion_mutations >= 1  # the preloader fades by inline style

    assert record.reel_seconds and record.reel_seconds > 3
    assert (folder / record.reel_file).stat().st_size > 0


def test_typography_twin_replaces_the_type_and_records_no_motion(fixture_site_url, fast_settings):
    record = _capture(fixture_site_url, fast_settings, Variant.TYPOGRAPHY)
    tokens = json.loads((fast_settings.capture_dir(record.capture_id) / TOKENS_FILE).read_text())

    assert record.status == CaptureStatus.OK, record.error
    assert tokens["fonts"][0]["family"] == "Arial"
    assert record.reel_file is None and record.metrics.reduced_motion_respected is None
    assert record.quality.passed, record.quality  # twins are not expected to have a reel


def test_an_age_gate_is_answered_and_the_page_behind_it_captured(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "age-gate.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert "gate:si" in record.overlay_actions
    assert [s.method for s in record.stills] == ["top", "native", "native", "native"]


def test_a_warning_gate_then_a_wheel_driven_slideshow(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "warning-slides.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert "gate:okay" in record.overlay_actions
    # each gesture moves one slide, and the slideshow ignores gestures while it animates
    assert [s.method for s in record.stills] == ["top", "wheel", "wheel", "wheel"]


def test_a_page_that_scrolls_an_inner_element(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "inner-scroll.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert [s.method for s in record.stills] == ["top", "inner", "inner", "inner"]
    assert [s.scroll_y for s in record.stills] == [0, 900, 1800, 2700]


def test_a_link_on_a_backdrop_is_not_a_gate(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "backdrop.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert not [a for a in record.overlay_actions if a.startswith(("gate:", "left-page"))]
    assert record.final_url.endswith("/backdrop.html")


def test_a_failed_transcode_keeps_the_capture(fixture_site_url, fast_settings, monkeypatch):
    def broken(*_args):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(reel, "_transcode", broken)
    fast_settings.capture.reduced_motion_check = False
    record = _capture(fixture_site_url, fast_settings)

    assert record.status == CaptureStatus.OK, record.error
    assert record.quality.reel_missing and "transcode-failed" in record.overlay_actions
    assert len(record.stills) == 4


def test_an_age_gate_whose_backdrop_sits_beside_its_box(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "age-modal.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert "gate:yes" in record.overlay_actions
    assert len(record.stills) == 4


def test_a_cookie_box_without_the_usual_names_is_accepted(fixture_site_url, fast_settings):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "cookie-box.html"), fast_settings)

    assert record.quality.passed, record.quality
    assert "popup:j'accepte" in record.overlay_actions  # a curly apostrophe on the page


def test_a_pop_up_that_appears_on_scroll_is_closed_before_the_next_still(
    fixture_site_url, fast_settings
):
    _stills_only(fast_settings)
    record = _capture(_sibling(fixture_site_url, "popup-late.html"), fast_settings)
    folder = fast_settings.capture_dir(record.capture_id)

    assert record.quality.passed, record.quality
    assert "popup:no thanks" in record.overlay_actions
    assert len(record.stills) == 4
    # the offer is the only white on the page: no still may show it
    for still in record.stills:
        grey = Image.open(folder / still.file).convert("L")
        white = sum(grey.histogram()[250:]) / (grey.width * grey.height)
        assert white < 0.01, still.file
