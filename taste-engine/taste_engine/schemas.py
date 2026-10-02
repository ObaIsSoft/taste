"""Data contracts shared by every stage. Records are validated when written."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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
