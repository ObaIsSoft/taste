import pytest

from taste_engine.capture import degrade, js
from taste_engine.capture.overlays import same_page, same_site
from taste_engine.capture.quality import assess
from taste_engine.schemas import Variant
from taste_engine.settings import CaptureSettings

CFG = CaptureSettings()


def _assess(**overrides):
    values = {
        "cfg": CFG,
        "requested_url": "https://studio.example.com/",
        "landed_url": "https://studio.example.com/",
        "final_url": "https://studio.example.com/",
        "http_status": 200,
        "title": "Studio",
        "text_sample": "x" * 5000,
        "hero_spread": 40.0,
        "consent_left": [],
        "gate_text": None,
        "clicked": True,
        "reel_expected": True,
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
        ({"final_url": "https://studio.example.com/private-service"}, "navigated_away"),
        ({"consent_left": ['[role="dialog"]']}, "overlay_remaining"),
        ({"reel_ok": False}, "reel_missing"),
        ({"http_status": 522}, "site_down"),
        ({"landed_url": "https://studio.example.com/lander"}, "parked"),
        ({"text_sample": "limlondon.com Get This Domain"}, "parked"),
        ({"title": "Top Crypto Casinos - No KYC Options"}, "spam"),
        ({"gate_text": "Rientri nell'età minima per consumare alcolici? NO SI"}, "gate_remaining"),
        ({"gate_text": "Heads up, this site contains flashing colors. Okay"}, "gate_remaining"),
    ],
)
def test_each_problem_fails_qa(overrides, flag):
    flags = _assess(**overrides)
    assert getattr(flags, flag)
    assert not flags.passed


def test_a_recaptcha_footer_is_not_a_bot_block():
    footer = "Contact us. This form is protected by reCAPTCHA and the Privacy Policy applies. " * 20
    assert _assess(text_sample=footer).passed


def test_a_block_page_title_is_a_bot_block():
    assert _assess(title="Access denied | example.com").bot_block


def test_a_down_site_is_not_called_blocked_but_a_challenge_is():
    down = _assess(http_status=522, title="maisonmargiela.digital | 522: Connection timed out")
    assert down.site_down and not down.bot_block
    challenge = _assess(
        http_status=503, title="Just a moment...", text_sample="checking your browser"
    )
    assert challenge.bot_block and not challenge.site_down


def test_a_site_that_moves_on_by_itself_is_not_flagged():
    intro = _assess(
        landed_url="https://studio.example.com/",
        final_url="https://studio.example.com/introduction/",
        clicked=False,
    )
    assert intro.passed


def test_a_closed_shopify_store_counts_as_parked():
    assert _assess(
        text_sample="This store is currently unavailable. Are you the store owner?"
    ).parked


def test_a_redirect_while_loading_is_fine_but_a_change_after_it_is_not():
    redirected = _assess(
        landed_url="https://studio.example.com/en", final_url="https://studio.example.com/en/"
    )
    assert redirected.passed
    moved = _assess(
        landed_url="https://studio.example.com/en", final_url="https://studio.example.com/en/work"
    )
    assert moved.navigated_away and "page changed after load" in moved.notes[0]


def test_a_full_screen_site_is_not_mistaken_for_a_gate():
    assert _assess(gate_text="Coming soon Films & Series Ads & Music Videos").passed


def test_twins_need_no_reel():
    assert _assess(reel_expected=False, reel_ok=False).passed


def test_a_casino_mention_in_long_copy_is_not_spam():
    assert _assess(
        text_sample="We designed the brand for a casino hotel in Macau. " + "x" * 3000
    ).passed


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


def test_same_page_ignores_a_trailing_slash_but_not_the_path():
    assert same_page("https://a.test/work/", "https://www.a.test/work")
    assert not same_page("https://a.test/work", "https://a.test/about")


def test_init_script_is_invoked_not_just_defined():
    script = js.init_script(10, 1.0).strip()
    assert script.startswith("(() =>") and script.endswith("})();")


def test_every_twin_has_a_profile_and_original_has_none():
    assert degrade.init_script(Variant.ORIGINAL) is None
    for variant in Variant:
        if variant is not Variant.ORIGINAL:
            assert degrade.init_script(variant).strip().endswith("})();")
