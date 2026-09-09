# PEAD successor-shell exposure: measured, not fixed (2026-09-10)

Follow-up to `edgar_submissions_store_2026-09-10/EDGAR_SUBMISSIONS_STORE_2026-09-10.md`
§5, which recorded the defect and deliberately left it unfixed. This measures how large
it is and what a fix could key on. **Nothing is changed by this work.**

## 1. The defect, restated

`cross_sectional_pead.load_cik_map` resolves tickers through SEC's current ticker → CIK
map with no successor-shell resolution. After a holding-company reorganisation that map
points at the newly registered successor, which holds none of the operating history.
`edgar_xbrl_provider` fixed this for companyfacts on 2026-09-02 (`dcdf864`) with a
trigger the submissions endpoint cannot reproduce: *the successor carries no annual XBRL
facts, so use the CIK that filed most of them*. Submissions carries a filing index, not
facts.

## 2. Exposure: 2 tickers of 503

Measured across every stored filing history (`measure_successor_shells.py`):

| | |
|---|---|
| tickers with stored filings | 503 of 503 |
| tickers whose entire stored history holds **zero 10-K** | **2** |

| ticker | CIK | filings | earliest | dominant forms |
|---|---|---|---|---|
| XOM | 2115436 | 29 | 2026-07-01 | S-8 POS ×23, 8-K ×3, 10-Q ×1, POSASR ×1, 8-K12B ×1 |
| HONA | 2089271 | 77 | 2025-10-01 | Form 4 ×34, Form 3 ×22, 8-K ×4, DRS/A ×3, SCHEDULE 13G ×2, S-8 ×2 |

10-K counts across the universe (capped at 10): 227 tickers hold 10 or more, 61 hold 9,
58 hold 8, and only these 2 hold none. The exposure is small and bounded.

## 3. The obvious trigger does not work

**"Zero 10-K" alone cannot be the rule.** It selects both tickers, and only one of them
is a successor shell:

* XOM's CIK 2115436 was registered 2026-07-01 and its filings are overwhelmingly
  post-effective amendments to employee-benefit-plan registrations (S-8 POS) — what a
  successor files when it assumes a predecessor's plans. The operating history is under
  CIK 34088.
* HONA's CIK 2089271 filed draft registration statements (DRS/A) and a burst of Forms 3
  and 4 — the fingerprint of a company that recently listed. There is no predecessor to
  redirect to, and redirecting it anywhere would be wrong.

This is the same wall `edgar_xbrl_provider`'s docstring already records: its trigger
"cannot be 'zero annual facts', and the measured population gives no basis for the
threshold such a rule would need."

## 4. A conjunction that separates them on this data

`8-K12B` appears in 26 of 503 stored histories, so **the form alone is not rare and is
not a shell signal**. But 25 of those 26 have also accumulated their own 10-K filings
(AON 13, FRT 21, ULTA 18, LIN 9, AVGO 8, …). The conjunction is what separates:

| test | XOM | HONA | rest of universe |
|---|---|---|---|
| zero 10-K | ✓ | ✓ | 0 of 501 |
| carries 8-K12B | ✓ | ✗ | 25 of 501 |
| **both** | **✓** | ✗ | **0 of 501** |

On this universe `n_10k == 0 AND any 8-K12B` selects exactly XOM and nothing else.

**This is one positive example. It is not a basis for adopting a rule**, and this memo
does not adopt one. What the interpretation of form 8-K12B is has not been verified
against SEC's own form documentation here; only where the form appears has been measured.
The 25 co-occurring tickers are consistent with the fact provider's documented
expectation that a successor stops looking like a shell once it files its own annual
report — but "consistent with" is not "established".

## 5. The cost of leaving it, stated so the decision is informed

XOM currently contributes 29 filings dated from 2026-07-01 to pead's sample instead of
two decades of announcements: one ticker of 503, its events almost entirely absent rather
than wrong. Against that, adopting a redirect rule from a single example risks
mis-redirecting a genuinely young registrant, which would attribute another company's
announcements to it — a wrong event is worse than a missing one for this family, whose
whole construction is event-date-based.

That asymmetry is the argument for leaving it until there is more evidence, and it is
the reason this memo stops at measurement.

## 6. A broader question this data raises and does not answer

Several of the 26 have their earliest stored filing well after this project's
2018-04-07 PEAD fetch floor (FERG 2024-03-01, PSKY 2024-11-04, APO 2021-05-07, APA
2021-03-01, MRVL 2020-12-22, CSCO 2020-05-13). That could mean their CIK is younger than
the operating company, or simply that `filings.recent` is bounded and their older rows
have already left the endpoint. **This measurement cannot distinguish the two**, because
both produce the same truncated history. Separating them would need SEC's
`filings.files` archives, which this project does not fetch. Logged as a follow-up, not
a finding.
