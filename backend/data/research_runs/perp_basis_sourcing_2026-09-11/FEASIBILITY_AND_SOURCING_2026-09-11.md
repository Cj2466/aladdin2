# Crypto perpetual-futures basis — feasibility and sourcing decision (orchestrator, 2026-09-11)

Block C of the 10-hour plan, done by the orchestrator (Fable 5.1) rather than a sub-agent because
every input had already been read for the hunting-ground review. Every number below is either from
the paper's extracted text (`../hunting_ground_review_2026-09-11/sources/perpetual_futures_
fundamentals.txt`, SHA-256 in that directory's `SOURCES.md`), from this repo's own files, or from a
live request made today and quoted.

## 1. Novelty check against `cross_sectional_funding_carry` (the pre-condition of this block)

The existing family (built 2026-08-29, honest negative: best spec DSR 0.761 at n_local, below the
0.95 bar) ranks Binance USDT perps by TRAILING FUNDING and goes short the highest-funding / long the
lowest-funding names, equal-weight, dollar-neutral in perp notional, UNHEDGED to spot. Its own
docstring says: "The papers above study single-name, delta-neutral carry (short perp vs long spot).
This family tests the CROSS-SECTIONAL version ... a genuinely different (and riskier) construction."

He et al.'s strategy (their §5 and Eq. 8) is the single-name, delta-neutral one: compute each
hour the annualized deviation ρ = κ(f − s) − r (κ = 1095, f/s = log perp/spot, r = Aave borrow or
supply rate), open long-spot/short-perp when ρ exceeds the fee-implied bound (High tier ±179%/yr,
Table 3), close when ρ first returns to 0; returns come mostly from PRICE CONVERGENCE, not funding
(their Table 9). Different state variable (basis level, not funding rank), different hedge (spot
leg), different horizon (hours, mean 135 h at High tier), different P&L source. **Verdict: not the
same mechanism; the earlier negative is not a prior on this one.** The BIS "Crypto Carry" finding
the earlier family cites — carry compressed ~3 pp after the spot-ETF launch — applies to both.

## 2. Data (verified live today, public Binance endpoints, no key)

| series | endpoint | earliest 1h bar | latest |
|---|---|---|---|
| spot BTCUSDT / ETHUSDT | api.binance.com /api/v3/klines | 2017-08-17 04:00 UTC | 2026-09-11 05:00 UTC |
| perp BTCUSDT | fapi.binance.com /fapi/v1/klines | 2019-09-08 17:00 UTC | 2026-09-11 05:00 UTC |
| perp ETHUSDT | same | 2019-11-27 07:00 UTC | same |

In the repo (`data/binance_futures/`, fetched through 2026-08-29): funding settlements and DAILY
perp klines for 146 symbols; no spot klines, no hourly bars. Hourly spot + perp for the five paper
coins is ~60k rows per series, ~60 requests each at the 1,000-row limit — feasible in minutes.
NOT held and not free-verified: the Aave USDT borrow/supply rate series the paper uses for r. Its
magnitude (single-digit %/yr) is small against the ±179%/yr bound, so a build could carry r as a
disclosed constant or a fetched DeFi series; not resolved here.

## 3. Fees (the input the whole claim hinges on)

The paper's High tier — "typically an individual trader" (Table 3) — is spot 6.75 bp and futures
1.44 bp per side, and the authors state they use MAKER fees "because institutions typically trade
maker orders" (§4). A retail participant executing at market pays TAKER fees, which are higher.
Binance's fee page (`binance.com/en/fee/trading`) returned 0 bytes to a plain fetch today
(JavaScript-rendered) and no Binance API key exists in `.env`, so today's actual schedule is
UNVERIFIED here. Venue access from Thailand: UNVERIFIED (same gap the review recorded).

## 4. Sourcing power pre-check (`sourcing_power_perp_basis.py`, output JSON beside it)

The paper annualizes a threshold strategy as (μ/σ)·√N_active (Lucca-Moench). Re-derived: with
zero return when flat, the hourly calendar series has mean a·μ and variance ≈ a·σ², so its
annualized Sharpe is √a·(μ/σ)·√8760 = (μ/σ)·√N_active — identical. The paper's Sharpe ratios
are therefore used as-is. (First pass multiplied by √active% a second time; caught on
re-derivation before anything was written down as a result.)

Ladder-rung n_local = 16 declared; bar 0.95; sigma_SR = √(365/n); `dsr_power_report` defaults.

| window | claim | BTC | ETH | BNB | DOGE | ADA |
|---|---|---|---|---|---|---|
| 7.0 y (paper in-sample + 2.5 y OOS) | Table 6 full | 0.905 | 0.999 | 1.000 | 1.000 | 1.000 |
| 7.0 y | Table 7 post-break 2022–23 mean | **0.052** | **0.200** | **0.070** | **0.076** | **0.132** |
| 2.5 y OOS only (2024-03 → 2026-09) | Table 6 full | 0.273 | 0.718 | 1.000 | 0.986 | 0.782 |
| 2.5 y OOS only | post-break | 0.009 | 0.029 | 0.012 | 0.012 | 0.020 |

**Decision: DECLINE_AT_SOURCING as a signal test.** The paper's own post-2022 numbers — the
regime it describes as a structural break, with the strategy active 0.02–3.8% of hours in
2022–23 — are undetectable at the 0.95 bar even with all seven years; the out-of-sample
window alone cannot certify even the full-sample claim for BTC/ETH/ADA. A build would replicate
the paper's in-sample years (already published) and then report an underpowered OOS tail — the
LETF outcome again, which the sourcing rule exists to prevent.

## 5. What is worth doing instead (cheap, descriptive, no DSR, no registration)

The open question the review left — "is the ground still alive after the 2024 revival the paper's
partial 2024 column shows (BTC SR 11.5 on 1,682 hours)?" — does not need a strategy backtest. It
needs the hourly ρ series itself, 2020 → today, for the five paper coins plus the 20 largest alt
perps by turnover, and a table of: share of hours beyond the High-tier bound by year, mean
excursion size, mean time-to-zero. That is a measurement of the OPPORTUNITY, not of a return, and
it decides whether a future pre-registration can claim any effect at all post-2024. Proposed as
Block C′ (Sonnet, ~1.5 h) if time permits after Block B merges; its numbers go into
`DECLINED_AT_SOURCING.md` next to this decision so the entry can be reopened on evidence.

## 6. Could not verify
Current Binance fee schedule (page is JS; no key); Thailand venue access; Aave rate history
availability; whether Binance's spot maker rebate/VIP structure today matches the paper's 2023
tiers; anything about exchanges other than Binance.
