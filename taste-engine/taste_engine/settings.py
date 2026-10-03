"""Single source of truth for paths and tunable values.

Every field can be overridden from the environment with the ``TASTE_`` prefix
(nested fields use ``__``, e.g. ``TASTE_CAPTURE__VIEWPORT_WIDTH=1920``) or from
``taste-engine/.env``. No other module may hardcode a path, a model id or a
threshold; ``tests/test_guardrails.py`` enforces this.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ReelSettings(BaseModel):
    """The scripted UX reel: the same choreography for every site."""

    enabled: bool = True  # originals only: twins need stills, not motion
    intro_s: float = 2.0  # the load and intro play untouched for at least this long
    intro_max_s: float = 12.0  # ...and until the page settles, up to this long
    max_s: float = 45.0  # a page too slow to finish the choreography in this long gets cut short
    scroll_px_per_s: float = 400.0  # slow enough for a designer to read
    pause_per_screen_s: float = 1.0
    screens: int = 3
    hover_targets: int = 3
    hover_move_steps: int = 12  # mouse moves in this many steps, like a hand would
    hover_dwell_s: float = 0.8
    menu_dwell_s: float = 1.5
    return_speedup: float = 2.0  # scrolling back to the top runs this much faster
    output_width: int = 960  # height follows the viewport; no voting pane shows it wider
    fps: int = 25  # Playwright records at 25 fps; any other rate duplicates or drops frames
    crf: int = 30  # with the width, about 0.45 MB a reel: 1,000 sites fit Supabase's free 1 GB
    preset: str = "veryfast"


class CaptureSettings(BaseModel):
    viewport_width: int = 1440
    viewport_height: int = 900
    screens: int = 4  # stills: the hero plus the next three screens
    locale: str = "en-US"
    timezone: str = "UTC"
    headless: bool = True
    # "chromium" is Chromium's full headless mode, which renders WebGL on the GPU; the default
    # headless shell renders it in software, which makes WebGL sites stutter in reels and metrics.
    browser_channel: str | None = "chromium"
    browser_executable: Path | None = None
    # Without this, navigator.webdriver is true, and bot walls such as Cloudflare refuse the page.
    browser_args: list[str] = Field(
        default_factory=lambda: ["--disable-blink-features=AutomationControlled"]
    )
    user_agent: str | None = None  # None: the browser's own, without "Headless" in it

    navigation_timeout_s: float = 60.0
    network_idle_timeout_s: float = 15.0
    settle_min_s: float = 1.0
    settle_max_s: float = 10.0
    settle_poll_s: float = 0.25
    screen_settle_s: float = 1.2
    action_timeout_s: float = 30.0  # screenshots and other page operations on heavy pages
    wheel_wait_s: float = 2.5  # how long a wheel-driven page gets to show its next screen
    wheel_attempts: int = 2  # slideshows often ignore a second gesture while they animate
    inner_scroll_min_px: int = 200  # an inner element scrolling this far counts as the page
    stable_diff: float = 1.5  # mean colour change (0-255) between polls that counts as still
    blank_std: float = 6.0  # colour spread below which a frame counts as blank
    jank_test_s: float = 2.5
    jank_wheel_px: int = 60
    jank_step_ms: int = 50
    frame_budget_ms: float = 1000 / 60
    dropped_frame_factor: float = 1.5  # a frame this many budgets long counts as dropped
    native_scroll_share: float = 0.2  # below this share of wheel distance, scroll is not native
    reduced_motion_check: bool = True  # originals only
    idle_motion_s: float = 2.0  # JavaScript motion is counted over this long with no input
    idle_motion_min: int = 10  # fewer style changes than this in that window is no motion
    text_sample_chars: int = 4000

    overlay_rounds: int = 3
    click_timeout_s: float = 2.5
    gate_cover_ratio: float = 0.6  # a fixed layer on top of this share of the screen blocks it
    gate_max_controls: int = 8  # a gate offers a few choices; more means it is the site itself
    gate_max_chars: int = 800  # ...and says little
    popup_min_area: float = 0.03  # a floating box smaller than this share of the screen is left
    popup_max_controls: int = 12  # more buttons than this is navigation, not a pop-up
    overlay_cover_ratio: float = 0.1  # consent UI this large left on screen fails QA
    accept_texts: list[str] = Field(
        default_factory=lambda: [
            "accept",
            "accept all",
            "accept all cookies",
            "accept cookies",
            "accept and close",
            "allow",
            "allow all",
            "allow all cookies",
            "allow cookies",
            "agree",
            "i agree",
            "agree and close",
            "yes, i agree",
            "got it",
            "ok",
            "okay",
            "i understand",
            "understood",
            "continue",
            "accepter",
            "tout accepter",
            "j'accepte",
            "accepter et fermer",
            "accepter tout",
            "tout accepter et fermer",
            "aceptar",
            "aceptar todo",
            "aceptar todas",
            "aceptar y cerrar",
            "aceptar cookies",
            "accetta",
            "accetta tutto",
            "accetta tutti",
            "accetta tutti i cookie",
            "accetta e chiudi",
            "accetto",
            "acconsento",
            "akzeptieren",
            "alle akzeptieren",
            "alle zulassen",
            "zustimmen",
            "alle cookies akzeptieren",
            "akzeptieren und schließen",
            "aceitar",
            "aceitar todos",
            "aceitar e fechar",
            "accepteren",
            "alles accepteren",
            "alle cookies accepteren",
            "akkoord",
        ]
    )
    # Answers that get past an intro, age or warning gate. Matched as whole labels, and only
    # inside the layer that blocks the page, so an "Explore" link on the page itself is safe.
    gate_texts: list[str] = Field(
        default_factory=lambda: [
            "enter",
            "enter site",
            "enter website",
            "enter the site",
            "enter experience",
            "click to enter",
            "tap to enter",
            "enter with sound",
            "enter without sound",
            "sound on",
            "sound off",
            "skip",
            "skip intro",
            "start",
            "start experience",
            "begin",
            "explore",
            "continue",
            "continue to site",
            "ok",
            "okay",
            "got it",
            "i understand",
            "i agree",
            "agree",
            "yes",
            "yes, i am",
            "i am over 18",
            "i'm over 18",
            "i am 18 or older",
            "i am of legal age",
            "i am over 21",
            "i'm over 21",
            "si",
            "sì",
            "sí",
            "oui",
            "ja",
            "sim",
            "entrer",
            "entrez",
            "découvrir",
            "entrar",
            "entra",
            "eintreten",
            "weiter",
            "continuar",
            "continua",
        ]
    )
    # Ways out of a pop-up that is not a gate: newsletter offers, quizzes, notices.
    dismiss_texts: list[str] = Field(
        default_factory=lambda: [
            "no thanks",
            "no, thanks",
            "no thank you",
            "not now",
            "maybe later",
            "not interested",
            "i'm not interested",
            "dismiss",
            "close",
            "×",
            "✕",
            "x",
            "continue without accepting",
            "continuer sans accepter",
            "chiudi",
            "fermer",
            "cerrar",
            "schließen",
            "sluiten",
            "fechar",
        ]
    )
    # Words that show a pop-up is about cookies, so its answer is an accept button.
    consent_cues: list[str] = Field(
        default_factory=lambda: [
            "cookie",
            "consent",
            "privacy",
            "gdpr",
            "données",
            "datenschutz",
            "privacidad",
            "riservatezza",
        ]
    )
    # Words that show a blocking layer is a gate, not a full-screen site.
    gate_cues: list[str] = Field(
        default_factory=lambda: [
            "age",
            "years",
            "18",
            "21",
            "legal",
            "alcohol",
            "drink",
            "enter",
            "sound",
            "warning",
            "heads up",
            "flashing",
            "epilep",
            "motion",
            "continue",
            "confirm",
            "verify",
            "età",
            "anni",
            "alcol",
            "âge",
            "edad",
            "alter",
            "alkohol",
        ]
    )
    consent_scopes: list[str] = Field(
        default_factory=lambda: [
            '[id*="cookie" i]',
            '[class*="cookie" i]',
            '[id*="consent" i]',
            '[class*="consent" i]',
            '[aria-label*="cookie" i]',
            '[aria-label*="consent" i]',
            '[role="dialog"]',
            '[aria-modal="true"]',
            "#onetrust-banner-sdk",
            "#CybotCookiebotDialog",
            ".cc-window",
            ".qc-cmp2-container",
            "#usercentrics-root",
        ]
    )
    bot_block_patterns: list[str] = Field(
        default_factory=lambda: [
            "automated access",
            "access denied",
            "are you a robot",
            "verify you are human",
            "checking your browser",
            "attention required",
            "captcha",
            "unusual traffic",
            "request blocked",
        ]
    )
    # A parked or for-sale domain: the award entry is long gone.
    parked_patterns: list[str] = Field(
        default_factory=lambda: [
            "domain is for sale",
            "domain may be for sale",
            "buy this domain",
            "get this domain",
            "make an offer on this domain",
            "looking for a domain",
            "domain has expired",
            "this domain is parked",
            "parked free",
            "hugedomains",
            "sedo domain parking",
            "this store is currently unavailable",
        ]
    )
    parked_paths: list[str] = Field(default_factory=lambda: ["/lander"])
    # A domain taken over by spam. Matched in the title, or this many times in the text.
    spam_patterns: list[str] = Field(
        default_factory=lambda: [
            "casino",
            "no kyc",
            "sportsbook",
            "betting site",
            "online slots",
            "online pokies",
            "payday loan",
            "viagra",
            "cialis",
        ]
    )
    spam_min_mentions: int = 3
    not_found_patterns: list[str] = Field(
        default_factory=lambda: [
            "page not found",
            "not found",
            "404",
            "page introuvable",
            "página no encontrada",
            "seite nicht gefunden",
            "pagina non trovata",
        ]
    )
    short_page_chars: int = 2500  # not-found phrases only count on pages this short
    bot_block_max_chars: int = 800  # block pages are near-empty; longer pages only match by title

    max_dom_elements: int = 4000
    max_animations: int = 300
    max_gsap_calls: int = 300
    gsap_poll_s: float = 15.0
    still_quality: int = 90
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    workers: int = 2
    attempts: int = 2
    retry_backoff_s: float = 5.0
    site_timeout_s: float = 300.0

    reel: ReelSettings = Field(default_factory=ReelSettings)


class AnalysisSettings(BaseModel):
    thumb_width: int = 360  # stills are measured at this width
    background_quant: int = 16  # colour bin size when finding the background colour
    background_tolerance: float = 24.0  # RGB distance that still counts as background
    palette_size: int = 8
    edge_threshold: float = 40.0  # luminance step that counts as an edge
    midline_tie_px: int = 8  # boxes centred this close to the middle count half on each side
    spacing_unit_px: int = 4  # spacing values on this grid count as regular


class ClaudeSettings(BaseModel):
    """Claude API use: descriptions now, the baseline judge and page generation later."""

    describe_model: str = "claude-opus-5-5"
    describe_effort: str = "low"
    describe_max_tokens: int = 4000
    image_max_width: int = 1024
    image_quality: int = 85
    batch_max_bytes: int = 200_000_000  # the Batch API limit is 256 MB
    batch_poll_s: float = 60.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASTE_",
        env_nested_delimiter="__",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    capture_version: str = "2.3.0"  # 2.3: pop-ups, backdrop gates, consent anywhere
    analysis_version: str = "2.1.0"  # 2.1: every capture metric reaches the features
    data_dir: Path = PROJECT_ROOT / "data"
    manifest_path: Path = PROJECT_ROOT / "manifest" / "sites.csv"
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    claude: ClaudeSettings = Field(default_factory=ClaudeSettings)

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "SUPABASE_KEY")
    )
    storage_bucket: str = "captures"  # private: the voting API hands out signed URLs
    # Claude's check that nothing covers the page and it is a live site (taste describe)
    publish_requires_description: bool = True
    voting_url: str | None = None  # the deployed voting site, for invite links

    @property
    def captures_dir(self) -> Path:
        return self.data_dir / "captures"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def votes_path(self) -> Path:
        return self.data_dir / "votes" / "votes.jsonl"

    def capture_dir(self, capture_id: str) -> Path:
        return self.captures_dir / capture_id


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
