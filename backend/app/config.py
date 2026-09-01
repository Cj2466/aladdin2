from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The two portfolio-construction methods this system can allocate with.
# Declared HERE rather than next to either optimizer because both optimizers
# live under app/services/, and app/services/ imports `settings` from this
# module — putting the names on the service side would make config.py import
# a service and close an import cycle.
#
# "mean_variance" is risk/optimizer.py's long-only SLSQP max-Sharpe with the
# DEFAULT_MAX_WEIGHT per-strategy cap: the method every existing code path
# uses, and the default everywhere.
# "hrp" is risk/hrp_optimizer.py's Hierarchical Risk Parity (Lopez de Prado
# 2016): covariance-structure-only, no matrix inversion, no weight cap.
OPTIMIZATION_METHOD_MEAN_VARIANCE = "mean_variance"
OPTIMIZATION_METHOD_HRP = "hrp"
OPTIMIZATION_METHODS = (OPTIMIZATION_METHOD_MEAN_VARIANCE, OPTIMIZATION_METHOD_HRP)


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
    # Which optimizer AutonomousPortfolioRunner reweights the system-owned
    # portfolio with. Defaults to "mean_variance" — the method that runner has
    # always used — so leaving this unset changes nothing; "hrp" is a
    # deliberate, explicit opt-in, never a silent replacement.
    #
    # Why the choice exists at all: at the small member counts this runner
    # actually operates at, the mean-variance path's own DEFAULT_MAX_WEIGHT
    # cap of 0.4 means at most ceil(1/0.4)=3 members can carry meaningful
    # weight, so below ~4 members it "can't discard anything" (measured, see
    # MIN_STRATEGIES_FOR_AUTONOMOUS_PORTFOLIO's comment in
    # autonomous_portfolio_runner.py). HRP has no cap and never inverts the
    # covariance matrix, so it gives every member a NON-ZERO weight instead
    # of leaving most at zero outside the cap's three slots. Which of those
    # is BETTER on this system's real data is an empirical question — hence
    # a toggle to A/B it, not a swap.
    #
    # Note the naive version of that argument does NOT survive measurement,
    # and the table below is why the wording above is "non-zero" rather than
    # "spread out": funding everything is not the same as being diversified.
    # By effective number of positions (inverse Herfindahl, 1/sum(w^2)) HRP
    # is MORE concentrated than capped mean-variance at every size tested —
    # 1.58 vs 2.78 at n=5 — because inverse-variance weighting piles into
    # the lowest-vol member. So HRP does not fix the "can't discard anything
    # at low n" limitation; it replaces a cap-shaped concentration with a
    # variance-shaped one.
    #
    # Whichever method actually produced a portfolio's stored weights is
    # recorded on StrategyPortfolio.last_optimization_method, so HRP-produced
    # weights are never indistinguishable from mean-variance-produced ones.
    #
    # MEASURED, 2026-08-28, on the real dev DB (230 distinct configs with a
    # stored status="ok" ExperimentRun; 40 random subsets per size; both
    # methods over the IDENTICAL build_returns_frame assembly; medians).
    # "Sharpe" is this codebase's own convention, (annualized return - 4% rf)
    # / annualized vol, which matters enormously below:
    #
    #   n     MV Sharpe / vol      HRP Sharpe / vol     MV->HRP turnover
    #    5    +0.32 / 0.111        -1.37 / 0.026        0.40 -> 0.13
    #    8    +0.71 / 0.105        -2.33 / 0.016        0.70 -> 0.12
    #   12    +1.17 / 0.096        -2.89 / 0.011        0.66 -> 0.30
    #   20    +1.45 / 0.087        -5.34 / 0.007        0.72 -> 0.22
    #   40    +1.78 / 0.059        -6.22 / 0.006        0.85 -> (refused)
    #
    # (turnover = half-to-half L1/2 weight change, fitting each half of the
    # overlap window separately: the paper's own stability claim.)
    #
    # INDEPENDENTLY RE-RUN, same day, different seed, same 230-config pool
    # and same 40-draws-per-size protocol — every conclusion below held, and
    # the effective-N row is new from that pass. "eff N" is the inverse
    # Herfindahl 1/sum(w^2), the effective number of positions:
    #
    #   n     MV Sharpe / vol      HRP Sharpe / vol    turnover  eff N MV/HRP
    #    5    +0.41 / 0.113        -1.29 / 0.026       0.52/0.11   2.78 / 1.58
    #    8    +0.82 / 0.110        -2.56 / 0.016       0.61/0.11   2.94 / 1.91
    #   12    +1.06 / 0.098        -2.57 / 0.013       0.74/0.20   3.35 / 1.82
    #   20    +1.50 / 0.086        -4.45 / 0.008       0.81/0.18   3.91 / 2.62
    #   40    +1.89 / 0.061        -5.99 / 0.006       0.78/(ref)  4.48 / 3.67
    #
    # HRP's stability claim REPLICATES — its weights move 2-6x less between
    # halves than mean-variance's (2.2-5.8x across the first table's sizes,
    # 3.7-5.6x across the second's; the RATIO is noisy, but mean-variance's
    # absolute turnover climbs with breadth while HRP's stays roughly flat,
    # so the gap itself widens), as hrp_optimizer.py's docstring says. But on
    # THIS system's current strategy set that stability is not worth having,
    # for a specific and explainable reason: HRP allocates by inverse
    # variance and this set is full of pair strategies that trade rarely, so
    # it piles into near-flat equity curves. On the 10 registrations actually
    # in the pipeline it put 61.7% into ou_pairs_v1 GOOG/GOOGL, whose
    # annualized vol is 0.75% and annualized return 0.21% (reproduced
    # exactly on the independent re-run, both tables' runs agreeing to the
    # basis point). The resulting portfolio isn't losing money — 0.45%/yr
    # at ~0.6% vol — it is essentially cash, and cash scores catastrophically
    # against a 4% risk-free rate. Out of sample (fit on the first half of
    # the window, evaluate on the second) mean-variance beat HRP at every
    # size tested — independently re-run, median OOS Sharpe MV vs HRP:
    # -0.31/-0.87 (n=5), +0.04/-1.36 (8), +0.35/-1.80 (12), +0.33/-2.38
    # (20), +0.85/-4.30 (40), with MV ahead on 21/33, 26/36, 17/20, 11/11
    # and 5/5 of individual draws. (Note MV's own OOS Sharpe is far below
    # its in-sample number — that is the ordinary overfitting penalty, and
    # it does not change the ORDERING, which is what this table is for.)
    #
    # Also measured: HRP REFUSES a member set containing a zero-variance
    # strategy (1 of the 230 configs is exactly flat over its full window;
    # flat-over-a-sub-window is far more common). Refusal rate rose from
    # 1/40 draws at n=5 to 13/40 at n=40 (1/40 -> 17/40 on the independent
    # re-run — same shape, different draws). Those refusals surface as
    # OptimizationInfeasibleError and the runner falls back to equal weight,
    # so they cost weights, not ticks.
    #
    # CONCLUSION AS OF THIS MEASUREMENT: leave this at mean_variance. The
    # toggle exists so the comparison can be re-run cheaply once the strategy
    # set changes character — HRP is the right tool for a set of comparably-
    # volatile return streams, which this is not yet.
    autonomous_portfolio_optimization_method: str = OPTIMIZATION_METHOD_MEAN_VARIANCE
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
    # --- Macro/commodity exposure betas ("Project 2", Layer 1) ---------------
    # Same daily cadence and same reasoning as membership_refresh above: the
    # inputs (yfinance EOD bars, FRED daily series) move at most once per
    # business day, so anything tighter is pure waste. A tick that finds the
    # table fresh is a single indexed MAX(as_of_date) query, so ticking daily
    # against a 7-day staleness bar costs essentially nothing.
    macro_beta_refresh_interval_seconds: int = 86400
    # A 252-day rolling beta moves very little when one day rolls on and one
    # rolls off — recomputing daily would rewrite ~6,500 rows to chase noise,
    # and since the table is APPEND-ONLY (see MacroCommodityBeta's docstring)
    # every needless recompute is a permanent generation, not an overwrite.
    # Weekly is the cadence the plan pre-declared and the pre-registration
    # froze. An EMPTY table counts as stale, so a first deploy computes
    # immediately rather than sitting idle.
    macro_beta_recompute_stale_after_days: int = 7
    # One trading year, matching the estimation window fixed in the family's
    # pre-registration. Changing this changes what future rows mean, which is
    # why window_days is snapshotted onto every row rather than being read
    # back from settings at query time.
    macro_beta_rolling_window_days: int = 252
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

    @field_validator("autonomous_portfolio_optimization_method")
    @classmethod
    def _validate_optimization_method(cls, v: str) -> str:
        """An unrecognized value is REFUSED at startup, not quietly coerced
        back to the default. A typo'd AUTONOMOUS_PORTFOLIO_OPTIMIZATION_METHOD
        that silently fell back would leave an operator believing they were
        running HRP while the mean-variance weights kept being written — the
        exact "you can't tell which method produced this" failure the
        last_optimization_method column exists to prevent."""
        normalized = v.strip().lower()
        if normalized not in OPTIMIZATION_METHODS:
            raise ValueError(
                f"unknown optimization method {v!r}; expected one of "
                f"{', '.join(OPTIMIZATION_METHODS)}"
            )
        return normalized

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
