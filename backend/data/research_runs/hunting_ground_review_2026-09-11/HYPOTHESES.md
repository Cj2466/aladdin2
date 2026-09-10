# HYPOTHESES — hunting-ground review, 2026-09-11

**Everything on this page is tier H: an idea with NO evidence claimed.** Nothing here is sourced,
nothing here should be quoted as a finding, and nothing here should enter a scorecard, a memo or a
decision without first being turned into a measurable question and tested. Where a hypothesis was
*prompted* by something I read, I say which source prompted it — that is a provenance note, not
evidence for the hypothesis.

---

## H1. The binding constraint on this project is bet count, not signal quality
The project has measured that a true Sharpe of 0.5 is uncertifiable in ~10 years of daily data. Every
documented winner in this review (Virtu >10,000 instruments; Medallion ~30m orders/yr; HFT firms)
operates at a bet count orders of magnitude higher. **Hypothesis**: the project should stop selecting
candidates by plausibility-of-mechanism and start selecting them by *bets per year*, treating anything
under ~1,000 independent bets/year as untestable-in-principle and declining it at the sourcing stage
rather than after a full build. *Prompted by*: sources #3, #4, #6 and the project's own power finding.
**No evidence that this reordering would have changed any of the 58 outcomes.**

## H2. The right search key is "friction too small to be worth an institution's attention"
Section 2 of the review establishes that documented winners win on structural position. **Hypothesis**:
a productive candidate-sourcing rule is to enumerate *frictions* (settlement, redemption, listing,
tax-year, index-reconstitution, exchange-rule, KYC, minimum-ticket) and ask for each whether the
profit available is under ~$5m/yr — small enough that no institution staffs it — rather than to
enumerate published anomalies. **No evidence** that such an enumeration yields anything.

## H3. Microcap costs may be materially lower for a $100k book than the literature assumes
Hou-Xue-Zhang dismiss microcap anomalies on cost grounds; Novy-Marx & Velikov measure costs that
assume institutional size. **Hypothesis**: at $100k, a patient limit-order participant may face
effective costs far below the spread-crossing costs those papers model, because it can be a *maker*
rather than a *taker* in a name where its whole position is one or two prints. **No evidence.** This
would need to be measured directly with the project's own fills, not assumed — and the Albers et al.
result (source #14) is a live warning that "be a maker" is not free: the orders that fill are the ones
you did not want filled. *Prompted by*: sources #16, #11, #14.

## H4. The 2022 perp-basis break may be a liquidity-provider-exit effect rather than crowding
He et al. attribute narrowing to competition, yet also connect the 2022 break to the collapse of
Alameda and Three Arrows — i.e. the *exit* of large arbitrage capital coincided with a *narrowing*
spread, which is backwards for a crowding story. **Hypothesis**: the post-2022 narrowing is driven by
exchange mechanism changes (funding-rate caps, cross-margin, better spot-perp linkage) rather than by
competing capital, and if so it is a permanent regime rather than a cycle. **No evidence.** I did not
read anything on exchange mechanism changes. *Prompted by*: source #9.

## H5. Prediction markets may be an "eternal supply of new markets" ground rather than a signal ground
The AFT paper found "a limited number of dependent markets" but expects that to grow "as arbitrageurs
develop more specialized strategies". **Hypothesis**: the durable structure in prediction markets is
not a persistent mispricing but a persistent *flow* of newly-created, logically-related markets whose
internal consistency has not yet been enforced — an edge whose half-life per market is short but whose
supply is renewed. If true, the correct capability to build is fast market-relationship *discovery*
(the AFT authors used an LLM for exactly this and reported it hitting reasoning loops), not price
forecasting. **No evidence** that this generalises beyond their sample. *Prompted by*: source #8.

## H6. SPAC bet count could be raised by widening beyond US SPACs
Ground 4 fails the frequency test at ~40 US SPAC IPOs/year. **Hypothesis**: the same
redemption-floor structure exists in non-US SPAC-like vehicles and in other trust-backed
listed instruments, and pooling them would raise bet count enough to make the family certifiable.
**No evidence** — I read nothing on non-US SPACs and do not know whether the redemption floor
transfers. Note the project's own recorded lesson from Coval-Stafford: paper cutoffs and structural
premises do **not** automatically transfer across regimes.

## H7. The project's 58 negatives may be worth re-reading as a map rather than a pile
Fifty-eight honest negatives, all in the one corner McLean & Pontiff measure the largest decay in, is
consistent with a *systematically mis-chosen search space* rather than 58 independent bad draws.
**Hypothesis**: tabulating the 58 by (bet count, cost sensitivity, capacity, whether the mechanism
requires a structural position) would show the failures clustering on one or two axes, and that
clustering would be more informative than any individual result. **No evidence** — I did not read the
58 results, only the directory listing was in scope. This is cheap to test and does not need new data.

## H8. Legal access may be the actual gate on three of the top five grounds
Grounds 1, 2 and 5 all depend on venue access whose legality for a Thailand-resident solo participant
I did not verify at all. **Hypothesis**: settling this question first would reorder the entire
ranking, possibly eliminating the top two. **No evidence** — this is flagged as a hypothesis rather
than a finding precisely because I read no regulatory document. See `COULD_NOT_VERIFY.md` §B.11.

## H9. Public small-trader track records are worthless as evidence until someone audits them
Bhardwaj-Gorton-Rouwenhorst found ~72% backfill and whole vanished track records in a *professional*
database with a vendor and a reputation to protect. **Hypothesis**: Collective2/Darwinex/Numerai-style
leaderboards have at least these defects and probably worse, and no number from them should ever enter
this project's reasoning. **No evidence specific to those platforms** — I found and read no study of
them (see `COULD_NOT_VERIFY.md` §B.9). The generalisation from CTAs to retail platforms is the
hypothesis; the CTA finding itself is T1 and is in the review proper.
