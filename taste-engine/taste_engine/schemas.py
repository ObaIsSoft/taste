"""Data contracts shared by every stage. Records are validated when written."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field


class Cohort(StrEnum):
    AWARD = "award"
    GENERATED = "generated"
    ORDINARY = "ordinary"


class SiteEntry(BaseModel):
    """One row of the site manifest. Ids are assigned once and never reused."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    url: HttpUrl | str
    cohort: Cohort
    category: str | None = None
    source: str | None = None
    notes: str | None = None


class Variant(StrEnum):
    """A capture of the original site, or a degraded twin with one dimension broken."""

    ORIGINAL = "original"
    TYPOGRAPHY = "typography"
    COLOUR = "colour"
    SPACING = "spacing"
    LAYOUT = "layout"


def capture_id(site_id: int, variant: Variant) -> str:
    return f"{site_id:04d}-{variant.value}"


class CaptureStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class Still(BaseModel):
    index: int
    file: str
    scroll_y: int
    method: str  # "top", "native" or "wheel"


class UXMetrics(BaseModel):
    content_visible_ms: float | None = None
    first_contentful_paint_ms: float | None = None
    largest_contentful_paint_ms: float | None = None
    cumulative_layout_shift: float | None = None
    long_task_count: int | None = None
    long_task_ms: float | None = None
    mean_frame_ms: float | None = None
    dropped_frame_ratio: float | None = None
    inline_motion_mutations: int | None = None
    scroll_hijacked: bool | None = None
    scroll_signals: list[str] = Field(default_factory=list)
    reduced_motion_respected: bool | None = None
    uses_reduced_motion_query: bool | None = None
    transfer_bytes: int | None = None
    request_count: int | None = None


class QualityFlags(BaseModel):
    blank_hero: bool = False
    bot_block: bool = False
    not_found: bool = False
    navigated_away: bool = False
    overlay_remaining: bool = False
    reel_missing: bool = False
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def passed(self) -> bool:
        return not (
            self.blank_hero
            or self.bot_block
            or self.not_found
            or self.navigated_away
            or self.overlay_remaining
            or self.reel_missing
        )


class CaptureRecord(BaseModel):
    """Everything known about one capture; written to capture.json in its folder."""

    capture_id: str
    site_id: int
    variant: Variant
    requested_url: str
    final_url: str | None = None
    http_status: int | None = None
    title: str | None = None
    status: CaptureStatus
    error: str | None = None
    capture_version: str
    captured_at: datetime
    duration_s: float
    viewport_width: int
    viewport_height: int
    page_height: int | None = None
    stills: list[Still] = Field(default_factory=list)
    reel_file: str | None = None
    poster_file: str | None = None
    reel_seconds: float | None = None
    overlay_actions: list[str] = Field(default_factory=list)
    libraries: dict[str, bool] = Field(default_factory=dict)
    animation_count: int = 0
    gsap_call_count: int = 0
    metrics: UXMetrics = Field(default_factory=UXMetrics)
    quality: QualityFlags = Field(default_factory=QualityFlags)
