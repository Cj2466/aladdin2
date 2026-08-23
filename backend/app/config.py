from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    finnhub_api_key: str = ""
    fred_api_key: str = ""
    database_url: str = "sqlite:///./aladdin2.db"
    allowed_origins: str = "http://localhost:5173"  # comma-separated
    cookie_secure: bool = False  # set true once served over https
    cookie_samesite: str = "lax"  # "none" required when frontend/backend are on different domains
    risk_free_rate: float = 0.04  # static annualized rate used for Sharpe ratio, not fetched live
    alert_check_interval_seconds: int = 300
    # EOD price data updates once/day, so alert_check_interval_seconds's
    # near-real-time cadence (sized for intraday price alerts) would be
    # ~100x too frequent for no benefit. 4x/day bounds the lag after a new
    # day's bar publishes while staying near-zero-cost on the other checks
    # (get_price_history_cached's own bounds-check makes a same-day repeat
    # a pure cache hit, not a re-fetch).
    forward_validation_check_interval_seconds: int = 21600
    # A sweep is something a user just submitted and is actively watching
    # progress on — a different scale entirely from
    # forward_validation_check_interval_seconds's patient months-long cadence.
    sweep_check_interval_seconds: int = 15
    resend_api_key: str = ""
    alert_email_from: str = "onboarding@resend.dev"  # Resend's shared sandbox sender
    # Used to build password-reset/verification email links. Must match the
    # frontend's real public origin in production (the Cloudflare Pages
    # domain, not the Render backend URL) or emailed links go nowhere.
    frontend_url: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _normalize_postgres_scheme(cls, v: str) -> str:
        """Neon (and most Postgres hosts) hand out plain postgres:// or
        postgresql:// URLs; SQLAlchemy needs postgresql+psycopg:// to select
        the psycopg3 driver instead of defaulting to psycopg2 (not
        installed). Normalizing here lets a host's raw connection string be
        pasted into DATABASE_URL unedited. No-op for sqlite:// URLs."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @field_validator("finnhub_api_key", "fred_api_key", "resend_api_key")
    @classmethod
    def _strip_whitespace(cls, v: str) -> str:
        """A host's environment-variable UI (or a copy-paste in general)
        can silently include a trailing newline or leading/trailing spaces
        around a pasted secret — the provider then sees that whitespace as
        part of the key and correctly rejects it as invalid, exactly what
        happened with a newline-corrupted FINNHUB_API_KEY on Render.
        Stripping here means a pasted secret works regardless of how it was
        entered, instead of failing in a way that looks like a code bug."""
        return v.strip()

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
