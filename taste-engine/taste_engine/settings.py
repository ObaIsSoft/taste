"""Single source of truth for paths and tunable values.

Every field can be overridden from the environment with the ``TASTE_`` prefix
(nested fields use ``__``, e.g. ``TASTE_CAPTURE__VIEWPORT_WIDTH=1920``) or from
``taste-engine/.env``. No other module may hardcode a path, a model id or a
threshold; ``tests/test_guardrails.py`` enforces this.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ReelSettings(BaseModel):
    """The scripted UX reel: the same choreography for every site."""

    enabled: bool = True
    intro_s: float = 4.0  # load and intro, untouched
    scroll_px_per_s: float = 400.0  # slow enough for a designer to read
    scroll_step_px: int = 40
    pause_per_screen_s: float = 1.0
    screens: int = 3
    hover_targets: int = 3
    hover_move_steps: int = 12  # mouse moves in this many steps, like a hand would
    hover_dwell_s: float = 0.8
    menu_dwell_s: float = 1.5
    return_speedup: float = 2.0  # scrolling back to the top runs this much faster
    output_width: int = 1152  # height follows the viewport's aspect ratio
    fps: int = 30
    crf: int = 28
    preset: str = "veryfast"
    poster_qscale: int = 3


class CaptureSettings(BaseModel):
    viewport_width: int = 1440
    viewport_height: int = 900
    screens: int = 4  # stills: the hero plus the next three screens
    locale: str = "en-US"
    timezone: str = "UTC"
    headless: bool = True
    browser_executable: Path | None = None
    browser_args: list[str] = Field(default_factory=list)

    navigation_timeout_s: float = 60.0
    network_idle_timeout_s: float = 15.0
    settle_min_s: float = 1.0
    settle_max_s: float = 10.0
    settle_poll_s: float = 0.25
    screen_settle_s: float = 1.2
    stable_diff: float = 1.5  # mean grey-level change between polls that counts as still
    blank_std: float = 6.0  # grey-level spread below which a frame counts as blank
    jank_test_s: float = 2.5
    jank_wheel_px: int = 60
    jank_step_ms: int = 50
    frame_budget_ms: float = 1000 / 60
    dropped_frame_factor: float = 1.5  # a frame this many budgets long counts as dropped
    native_scroll_share: float = 0.2  # below this share of wheel distance, scroll is not native
    reduced_motion_check: bool = True
    text_sample_chars: int = 4000

    overlay_rounds: int = 3
    click_timeout_s: float = 2.5
    gate_cover_ratio: float = 0.6  # an overlay this large means the page is gated
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
            "aceptar",
            "aceptar todo",
            "aceptar todas",
            "accetta",
            "accetta tutto",
            "akzeptieren",
            "alle akzeptieren",
            "alle zulassen",
            "zustimmen",
            "aceitar",
            "aceitar todos",
            "accepteren",
            "alles accepteren",
        ]
    )
    gate_texts: list[str] = Field(
        default_factory=lambda: [
            "enter",
            "enter site",
            "enter website",
            "enter the site",
            "enter experience",
            "click to enter",
            "tap to enter",
            "explore",
            "start",
            "start experience",
            "begin",
            "skip",
            "skip intro",
            "continue to site",
            "enter with sound",
            "enter without sound",
            "sound on",
            "sound off",
            "entrer",
            "découvrir",
            "entrar",
            "eintreten",
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
    short_page_chars: int = 2500  # text pattern checks only apply to pages this short

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASTE_",
        env_nested_delimiter="__",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    capture_version: str = "2.0.0"
    data_dir: Path = PROJECT_ROOT / "data"
    manifest_path: Path = PROJECT_ROOT / "manifest" / "sites.csv"
    capture: CaptureSettings = Field(default_factory=CaptureSettings)

    @property
    def captures_dir(self) -> Path:
        return self.data_dir / "captures"

    def capture_dir(self, capture_id: str) -> Path:
        return self.captures_dir / capture_id


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
