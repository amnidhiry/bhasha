from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BHASHA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./bhasha.db"
    # Recall probability at or above which a word counts as known for coverage.
    known_threshold: float = 0.9
    desired_retention: float = 0.9
    max_reviews_per_day: int = 200
    max_new_cards_per_day: int = 15
    # Default target known-word coverage for generated and imported texts.
    target_coverage: float = 0.96
    # HSK list version used as the curriculum spine (see docs/design.md).
    hsk_version: str = "hsk3-2025"
    # IANA zone that defines "today" for daily caps and the sibling-facet rule.
    timezone: str = "UTC"
    # Built PWA to serve at / (empty or missing directory = API only).
    web_dir: str = "web"


@lru_cache
def get_settings() -> Settings:
    return Settings()
