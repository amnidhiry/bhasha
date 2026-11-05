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
    # Encrypts stored sign-in tokens and API keys. `openssl rand -hex 32`.
    secret_key: str = ""
    # LLM gateway safety cap: model calls per day across all features.
    llm_max_calls_per_day: int = 300
    # Loopback redirect for "Sign in with ChatGPT". Nothing needs to listen there:
    # you paste the address the browser lands on back into the app.
    chatgpt_redirect_port: int = 1455
    chatgpt_auth_url: str = "https://auth.openai.com"
    chatgpt_api_url: str = "https://api.openai.com/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
