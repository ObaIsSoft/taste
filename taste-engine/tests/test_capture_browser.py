"""End-to-end capture against a local fixture site. Needs Playwright browsers and ffmpeg."""

import json

import pytest

from taste_engine.capture.site import TOKENS_FILE, capture_site
from taste_engine.schemas import CaptureStatus, Cohort, SiteEntry, Variant

pytestmark = pytest.mark.browser


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

    assert record.reel_seconds and record.reel_seconds > 3
    assert (folder / record.reel_file).stat().st_size > 0
    assert (folder / record.poster_file).exists()


def test_typography_twin_replaces_the_type(fixture_site_url, fast_settings):
    entry = SiteEntry(id=1, url=fixture_site_url, cohort=Cohort.AWARD)
    fast_settings.capture.reel.enabled = False
    fast_settings.capture.reduced_motion_check = False
    record = capture_site(entry, Variant.TYPOGRAPHY, fast_settings)
    tokens = json.loads((fast_settings.capture_dir(record.capture_id) / TOKENS_FILE).read_text())

    assert record.status == CaptureStatus.OK, record.error
    assert tokens["fonts"][0]["family"] == "Arial"
