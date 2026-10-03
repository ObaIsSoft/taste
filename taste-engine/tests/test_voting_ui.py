"""The voting page in a real browser, against the real API with a fake database.

Set TASTE_UI_SHOTS to a folder to keep screenshots of each screen size.
"""

import base64
import importlib.util
import io
import itertools
import os
import re
import threading
from pathlib import Path

import pytest
from fakes import FakeSupabase
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

pytestmark = pytest.mark.browser

API_PATH = Path(__file__).parent.parent / "web" / "api" / "index.py"
SIDE_IDS = ("left", "right")
VISUAL = ["whitespace", "typography", "colour", "layout", "imagery", "cohesion"]


def _still(colour, label):
    image = Image.new("RGB", (1440, 900), colour)
    ImageDraw.Draw(image).text((60, 60), label, fill="white")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


class VotingFake(FakeSupabase):
    def __init__(self):
        super().__init__()
        self.tokens = itertools.count(1)
        self.reason_requested = True
        self.tables["dimensions"] = [
            {
                "id": d,
                "label": d.title(),
                "description": f"About {d}.",
                "round": "visual",
                "position": i,
            }
            for i, d in enumerate(VISUAL, 1)
        ]
        self.images = {
            "0001-original/screen-1.jpg": _still("#1d4ed8", "Left site"),
            "0002-original/screen-1.jpg": _still("#b45309", "Right site"),
        }

    def rpc(self, name, params):
        if name == "next_pair":
            self.rpc_results[name] = {
                "token": f"t-{next(self.tokens)}",
                "left_capture": "0001-original",
                "right_capture": "0002-original",
                "reason_requested": self.reason_requested,
            }
        elif name == "cast_vote":
            self.rpc_results[name] = 1
        elif name == "voter_progress":
            self.rpc_results[name] = [
                {
                    "round": "visual",
                    "calibration_done": 3,
                    "calibration_total": 91,
                    "votes": 3,
                    "target": 200,
                },
                {
                    "round": "motion",
                    "calibration_done": 0,
                    "calibration_total": 0,
                    "votes": 0,
                    "target": 200,
                },
            ]
        return super().rpc(name, params)

    def create_signed_urls(self, paths, _seconds):
        return [{"path": p, "signedURL": self.images.get(p, ""), "error": None} for p in paths]

    def votes(self):
        return [params for name, params in self.calls if name == "cast_vote"]

    def events(self):
        return [params["p_kind"] for name, params in self.calls if name == "log_event"]


@pytest.fixture
def site(monkeypatch):
    spec = importlib.util.spec_from_file_location("voting_api_ui", API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fake = VotingFake()
    monkeypatch.setattr(module, "db", lambda: fake)
    monkeypatch.setenv("TASTE_STORAGE_BUCKET", "captures")
    server = make_server("127.0.0.1", 0, module.app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", fake
    server.shutdown()


def _wait_for_votes(page, fake, count):
    for _ in range(50):
        if len(fake.votes()) >= count:
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"expected {count} votes, got {len(fake.votes())}")


def _open_round(page, url, round_name="Visual round", width=1440, height=900):
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("localStorage.setItem('taste.inviteCode', 'code-ada')")
    page.goto(url)
    page.get_by_role("button", name=round_name).click()
    expect(page.locator("#card-left .media > *")).to_be_visible()


def test_sign_in_and_vote(site):
    url, fake = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.get_by_label("Invite code").fill("code-ada")
        page.get_by_role("button", name="Start").click()
        expect(page.get_by_role("heading", name="Hi Ada. Choose a round.")).to_be_visible()
        expect(page.locator(".round-progress[data-round=visual]")).to_have_text(
            "Calibration 3 of 91"
        )

        page.get_by_role("button", name="Visual round").click()
        expect(page.get_by_role("img", name="Site A, screen 1")).to_be_visible()
        expect(page.locator("#progress")).to_have_text("Calibration 3 of 91")

        page.get_by_role("button", name="A is better").click()
        expect(page.get_by_text("What made A better?")).to_be_visible()
        page.get_by_role("button", name="Submit vote").click()
        expect(page.locator("#message")).to_have_text(
            "Say what decided it: pick one, or use your own words."
        )
        page.get_by_role("button", name="Typography").click()
        page.get_by_role("button", name="Submit vote").click()
        expect(page.locator("#message")).to_contain_text("Write a reason of at least 10")
        page.get_by_label("Why?").fill("One large headline over quiet body text.")
        page.get_by_role("button", name="Submit vote").click()
        _wait_for_votes(page, fake, 1)
        first = fake.votes()[0]
        assert first["p_token"] == "t-1" and first["p_outcome"] == "left"
        assert first["p_dimensions"] == ["typography"]
        expect(page.get_by_role("button", name="A is better")).to_be_visible()  # back to step one
        expect(page.get_by_label("Why?")).to_have_value("")  # the next pair starts clean

        page.keyboard.press("s")  # can't decide also asks what made it hard, optionally
        expect(page.get_by_text("What makes it hard to decide?")).to_be_visible()
        page.keyboard.press("Enter")
        _wait_for_votes(page, fake, 2)
        assert fake.votes()[1]["p_outcome"] == "cant_decide"
        assert fake.votes()[1]["p_token"] == "t-2"
        assert fake.votes()[1]["p_dimensions"] == []
        browser.close()


def test_keyboard_voting(site):
    url, fake = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url)

        page.keyboard.press("2")
        expect(page.get_by_text("What made B better?")).to_be_visible()
        expect(page.locator("#card-right")).to_have_class(re.compile(r"\bis-picked\b"))
        page.keyboard.press("1")
        page.keyboard.press("3")
        page.keyboard.press("3")  # pressing a number again un-picks it
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="B is better")).to_be_visible()

        page.keyboard.press("2")
        page.keyboard.press("1")
        page.get_by_label("Why?").fill("The grid holds every section together.")
        page.keyboard.press("Control+Enter")
        _wait_for_votes(page, fake, 1)
        vote = fake.votes()[0]
        assert vote["p_outcome"] == "right" and vote["p_dimensions"] == ["whitespace"]
        browser.close()


def test_reporting_a_broken_capture_asks_first(site):
    url, fake = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url)

        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#card-left").get_by_role("button", name="Report").click()
        page.wait_for_timeout(300)
        assert fake.votes() == []

        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#card-left").get_by_role("button", name="Report").click()
        _wait_for_votes(page, fake, 1)
        assert fake.votes()[0]["p_outcome"] == "broken_left"
        browser.close()


def test_invite_link_signs_in_and_leaves_the_address_bar(site):
    url, _ = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(f"{url}/#invite=code-ada")
        expect(page.get_by_role("heading", name="Hi Ada. Choose a round.")).to_be_visible()
        assert page.evaluate("location.hash") == ""
        assert page.evaluate("localStorage.getItem('taste.inviteCode')") == "code-ada"
        browser.close()


@pytest.mark.parametrize(
    ("width", "height", "both_visible"),
    [(390, 844, False), (820, 1180, True), (1440, 900, True), (1920, 1080, True)],
)
def test_layout_at_each_screen_size(site, width, height, both_visible):
    url, _ = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url, width=width, height=height)

        assert page.locator("#card-left").is_visible()
        assert page.locator("#card-right").is_visible() is both_visible
        assert page.locator(".side-switch").is_visible() is not both_visible
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        # the sites get most of the screen, and every control fits without scrolling
        assert page.locator(".panes").bounding_box()["height"] >= 0.55 * height
        decision = page.locator("#vote-form").bounding_box()
        assert decision["y"] + decision["height"] <= height + 1
        if not both_visible:
            page.get_by_role("tab", name="Site B").click()
            assert page.locator("#card-right").is_visible()
            assert not page.locator("#card-left").is_visible()

        shots = os.environ.get("TASTE_UI_SHOTS")
        if shots:
            page.screenshot(path=str(Path(shots) / f"voting-{width}.png"))
            page.get_by_role("button", name="A is better").click()
            page.screenshot(path=str(Path(shots) / f"voting-{width}-explain.png"))
        browser.close()


@pytest.mark.parametrize(
    ("round_name", "both_visible"), [("Motion round", True), ("Visual round", False)]
)
def test_phones_stack_recordings_but_tab_between_screens(site, round_name, both_visible):
    url, fake = site
    fake.images["0001-original/reel.mp4"] = "data:video/mp4;base64,AAAA"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url, round_name, 390, 844)

        assert page.locator("#card-right").is_visible() is both_visible
        assert page.locator(".side-switch").is_visible() is not both_visible
        if both_visible:
            expect(page.locator("#card-left video")).to_be_visible()
            left, right = (page.locator(f"#card-{s}").bounding_box() for s in SIDE_IDS)
            assert left["y"] + left["height"] <= right["y"]  # A above B
            assert left["width"] == right["width"] > 340  # each as wide as the screen allows
        decision = page.locator("#vote-form").bounding_box()
        assert decision["y"] + decision["height"] <= 844 + 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        shots = os.environ.get("TASTE_UI_SHOTS")
        if shots:
            page.screenshot(path=str(Path(shots) / f"phone-{round_name.split()[0].lower()}.png"))
        browser.close()


def test_designers_can_say_it_in_their_own_words(site):
    url, fake = site
    fake.rpc_results["voter_terms"] = [{"term": "editorial pacing", "uses": 3}]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url)

        page.get_by_role("button", name="B is better").click()
        words = page.get_by_label("Your own words")
        expect(page.locator("#own-term-list option")).to_have_attribute("value", "editorial pacing")
        words.fill("tension between serif and grotesk")
        words.press("Enter")  # adds the words; it does not submit the vote
        expect(
            page.get_by_role("button", name='Remove "tension between serif and grotesk"')
        ).to_be_visible()
        assert fake.votes() == []
        words.fill("editorial pacing")  # typed but not added: kept when the vote is submitted
        page.get_by_label("Why?").fill("The serif headline carries the page on its own.")
        page.get_by_role("button", name="Submit vote").click()
        _wait_for_votes(page, fake, 1)
        vote = fake.votes()[0]
        assert vote["p_outcome"] == "right" and vote["p_dimensions"] == []
        assert vote["p_terms"] == ["tension between serif and grotesk", "editorial pacing"]
        browser.close()


def test_the_reason_box_is_always_there_and_optional_unless_asked(site):
    url, fake = site
    fake.reason_requested = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url)

        page.get_by_role("button", name="A is better").click()
        expect(page.get_by_label("Why?")).to_be_visible()
        expect(page.locator("#reason-hint")).to_have_text("(optional)")
        page.get_by_role("button", name="Typography").click()
        page.get_by_role("button", name="Submit vote").click()  # no reason needed
        _wait_for_votes(page, fake, 1)
        assert fake.votes()[0]["p_reason"] is None
        browser.close()


def test_how_each_vote_was_seen_is_recorded(site):
    url, fake = site
    screens = [f"0002-original/screen-{i}.jpg" for i in range(1, 5)]  # enough to scroll
    fake.tables["captures"][1]["stills"] = screens
    fake.images.update({path: _still("#b45309", path) for path in screens})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url, width=390, height=844)

        page.get_by_role("tab", name="Site B").click()  # on a phone, opening B is an event
        page.locator("#card-right .strip").evaluate("strip => strip.scrollTop = 400")
        for _ in range(20):
            if {"view_right", "scroll_right"} <= set(fake.events()):
                break
            page.wait_for_timeout(100)
        assert {"view_right", "scroll_right"} <= set(fake.events())

        page.keyboard.press("s")
        page.keyboard.press("Enter")
        _wait_for_votes(page, fake, 1)
        details = fake.votes()[0]["p_client"]
        assert details["layout"] == "tabs" and details["pointer"] in ("coarse", "fine")
        assert details["viewport_width"] == 390 and details["index"] == 1 and details["session"]
        browser.close()


def test_equally_good_can_say_why_and_chips_carry_their_definition(site):
    url, fake = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        _open_round(page, url)

        page.get_by_role("button", name="Equally good").click()
        expect(page.get_by_text("What makes them equally good?")).to_be_visible()
        chip = page.get_by_role("button", name="Typography")
        expect(chip).to_have_attribute("title", "About typography.")
        chip.click()
        page.get_by_label("Why?").fill("Both carry the page on a single typeface.")
        page.get_by_role("button", name="Submit vote").click()
        _wait_for_votes(page, fake, 1)
        vote = fake.votes()[0]
        assert vote["p_outcome"] == "equally_good" and vote["p_dimensions"] == ["typography"]
        assert vote["p_reason"] == "Both carry the page on a single typeface."
        browser.close()


def test_the_guide_shows_the_numbers_and_definitions_from_the_database(site):
    url, _ = site
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(f"{url}/guide.html")
        expect(page.locator('[data-dimensions="visual"] dd').first).to_have_text(
            "About whitespace."
        )
        expect(page.locator('[data-fact="rounds.motion.target_votes"]')).to_have_text("100")
        expect(page.locator('[data-fact="rounds.visual.calibration_pairs"]')).to_have_text("91")
        browser.close()
