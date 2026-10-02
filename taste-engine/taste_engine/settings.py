"""Single source of truth for paths and tunable values.

Every field can be overridden from the environment with the ``TASTE_`` prefix
(nested fields use ``__``, e.g. ``TASTE_CAPTURE__VIEWPORT_WIDTH=1920``) or from
``taste-engine/.env``. No other module may hardcode a path, a model id or a
threshold; ``tests/test_guardrails.py`` enforces this.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASTE_",
        env_nested_delimiter="__",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    data_dir: Path = PROJECT_ROOT / "data"
    manifest_path: Path = PROJECT_ROOT / "manifest" / "sites.csv"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
