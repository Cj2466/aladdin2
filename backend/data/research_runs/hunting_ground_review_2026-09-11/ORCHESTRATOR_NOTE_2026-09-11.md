# Orchestrator verification note — hunting-ground review (Fable 5.1, 2026-09-11)

**Verified:** SHA-256 of all 16 extracted source texts matches `sources/SOURCES.md` (16/16).
Spot-checked against the extracted text, found as stated: Chague et al. "97% of all investors who
persisted for more than 300 days lost money" (l. 17, 293); Virtu S-1 "only one losing trading day
... 1,238 trading days" (l. 274); Gahng-Ritter-Zhang 23.9% / 23.6% / 0.51% (l. 169-177, 712-725);
Bhardwaj-Gorton-Rouwenhorst 46,785 backfilled observations (l. 112); He et al. Table 3 "High fees
... typically an individual trader" (l. 872) and BTC annualised Sharpe 2.00 (l. 1988); Albers et al.
"highly unprofitable" and "would only deteriorate with less favorable fees" (l. 526, 1013); Hou-Xue-
Zhang 447 anomalies (l. 71, 408); Polymarket AFT 2025 top account $2,009,631.76 (l. 1119).

**One qualification the agent's summary understates:** the Polymarket totals are computed
"assuming an ε = $1 profit per trade" (l. 1117) — a modelling assumption inside the paper, not an
audited realised P&L. The $39.6M / $2.0M figures are the paper's estimates under that assumption
and should be cited as such (the ranked CSV's "REALISED" wording is stronger than the source).

**Not re-verified by me:** any URL beyond the SHA check; the paywalled items the agent lists in
`COULD_NOT_VERIFY.md`; the legal-access question (B.11), which is the owner's.

**Orchestrator reading of the map (judgment, not evidence):** grounds 1 (perp basis) and 3
(microcap corner) are the two this project can act on with data it already holds or has already
priced (the delisted-securities gap gates ground 3 and should be re-surfaced now). Ground 2
(Polymarket) is gated on legal access and on-chain execution infrastructure the project does not
have. Ground 4 (SPACs) fails the bet-count test at current issuance. Hypothesis H1 (source
candidates by bets-per-year first) is consistent with the criteria audit of 2026-09-09 and is
recommended for adoption as a sourcing rule; H7 (tabulate the 58 negatives by bet count / cost
sensitivity / capacity) is cheap and recommended before the next candidate.
