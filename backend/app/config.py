from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    finnhub_api_key: str = ""
    fred_api_key: str = ""
    # Alpaca credentials -- Phase B (intraday market data) and Phase 5
    # (paper/live execution) share the same three fields, declared once
    # below under "Execution (Phase 5)" rather than twice; Phase B's
    # market-data client reads them just as read-only credentials and
    # never touches alpaca_live_trading_confirmed.
    database_url: str = "sqlite:///./aladdin2.db"
    allowed_origins: str = "http://localhost:5173"  # comma-separated
    cookie_secure: bool = False  # set true once served over https
    cookie_samesite: str = "lax"  # "none" required when frontend/backend are on different domains
    risk_free_rate: float = 0.04  # static annualized rate used for Sharpe ratio, not fetched live
    alert_check_interval_seconds: int = 300
    # A tick that finds no new trading day is a cheap cache-hit no-op
    # (get_price_history_cached's own bounds-check makes a same-day repeat
    # a pure cache read, not a re-fetch) — so there's no real cost to
    # checking often; this bounds how long a freshly-published EOD bar sits
    # unprocessed before the next tick picks it up.
    forward_validation_check_interval_seconds: int = 1800
    # A sweep is something a user just submitted and is actively watching
    # progress on. Paired with SweepRunner.BATCH_SIZE.
    sweep_check_interval_seconds: int = 5
    # A screening job is something a user just submitted and is actively
    # watching, like a sweep — but unlike a sweep it's a single indivisible
    # unit of work that typically completes within one tick (empirically
    # ~9-11s for the whole universe fetch+score at 503 tickers), so this
    # interval mainly controls how long a freshly-queued job sits before
    # the runner notices it.
    screening_check_interval_seconds: int = 5
    # Nobody watches this runner in real time the way a user watches a
    # just-submitted sweep — a new trading day only happens once/day, so a
    # no-op tick (checking "did we already run today") costing a handful of
    # indexed SELECTs is cheap to run often. Same value/reasoning as
    # forward_validation_check_interval_seconds.
    autonomous_research_check_interval_seconds: int = 1800
    # Same value and reasoning as forward_validation_check_interval_seconds
    # / autonomous_research_check_interval_seconds: nobody watches this
    # runner in real time, and a no-op tick is a handful of indexed SELECTs.
    #
    # Membership sync (add a just-graduated registration, drop one just
    # flagged underperforming) runs on EVERY tick — reacting quickly to a
    # prune is the safe direction. Re-optimization is separately capped at
    # once per calendar day by StrategyPortfolio.last_optimized_at.
    #
    # That cap is NOT a cost bound, and shouldn't be described as one:
    # measured against the real dev DB, one optimization runs in 4ms at 3
    # members and 51ms across all 43 stored "ok" runs, with no network call
    # at all (every input is already in results_json). It exists because the
    # inputs genuinely only change once a day — a registration advances at
    # most one trading day per ForwardValidationRunner tick, and each
    # member's freshest ExperimentRun is regenerated once a day by
    # AutonomousResearchRunner. Re-optimizing 48x a day would rewrite the
    # same weights 48 times from the same data.
    autonomous_portfolio_check_interval_seconds: int = 1800
    # Point-in-time S&P 500 membership moves a handful of times a month at
    # most, and the fastest of its three sources (SPY's holdings file)
    # republishes once per business day — so anything under a day is pure
    # waste, including a 5.5 MB re-download of the upstream point-in-time
    # file. A refresh keeps no database state, so a missed tick costs
    # nothing but freshness.
    membership_refresh_interval_seconds: int = 86400
    # Used instead of the above when a tick accepted nothing (a source was
    # down, or the fetched data failed validation), so a transient outage
    # doesn't cost a full day of freshness.
    membership_refresh_retry_interval_seconds: int = 3600
    # Owns ScreeningJob/ExperimentRun rows created by AutonomousResearchRunner,
    # not a real login-able account — never receives real email.
    system_account_email: str = "system+research@aladdin2.internal"
    resend_api_key: str = ""
    alert_email_from: str = "onboarding@resend.dev"  # Resend's shared sandbox sender

    # --- Execution (Phase 5) -------------------------------------------------
    # Broker credentials. Paper trading is the default and going live requires
    # BOTH alpaca_paper_trading=False AND alpaca_live_trading_confirmed=True —
    # two independently-named flags, so one accidental env edit (or a stray
    # ALPACA_PAPER_TRADING=false in a copied .env) can never by itself point
    # this system at real money.
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_paper_trading: bool = True
    alpaca_live_trading_confirmed: bool = False
    # Tight enough that a kill-switch flip or a loss-breach takes effect
    # within ~1 minute; not as tight as sweep/screening's 5s, since nobody is
    # watching a progress spinner here.
    execution_check_interval_seconds: int = 60
    # This system may only ever deploy half the account, a second line of
    # defense entirely independent of the optimizer's own weights.
    execution_capital_fraction: float = 0.5
    # Hard dollar ceilings, deliberately NOT redundant with the optimizer's
    # DEFAULT_MAX_WEIGHT: that is a fraction, so it scales up with equity (or
    # with a bug that inflates an equity reading). These do not.
    execution_max_position_notional: float = 1000.0
    execution_max_total_notional: float = 5000.0
    execution_daily_loss_limit_pct: float = 0.03
    execution_min_order_notional: float = 5.0
    execution_alert_email: str = ""
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

    @field_validator("finnhub_api_key", "fred_api_key", "resend_api_key", "alpaca_api_key", "alpaca_api_secret")
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
