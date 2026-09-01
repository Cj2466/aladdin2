"""Unit tests for the Lazy Prices filing-language family — this codebase's
first text/NLP family.

Mirrors test_cross_sectional_pead.py's structure: synthetic fixtures for the
pure math and the pure text logic, a stub text provider for the pipeline
paths, and NO live network calls. The real EDGAR shapes and the real
similarity behaviour on actual filings were verified LIVE on 2026-09-01 during
the build session (see data/research_runs/lazy_prices_2026-09-01_preregistration.txt
section 3); CI never touches SEC.

Three of these tests exist because the pre-registration named them as the
things that would make a positive result fake, and they are marked as such:
  * same-type-only pairing (never 10-K vs 10-Q)
  * point-in-time visibility (a similarity is unusable before its filing was
    accepted, and never keyed to the fiscal period end)
  * no corpus-fitted weighting (pairwise metrics only, so nothing can leak
    from the future of a formation date)
"""

from collections import Counter
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.market_data.edgar_filing_text_provider import FilingRef
from app.services.research_lab.cross_sectional import (
    CrossSectionalConfig,
    CrossSectionalData,
    fixed_universe_membership,
)
from app.services.research_lab.cross_sectional_lazy_prices import (
    LAZY_PRICES_CITATION,
    LAZY_PRICES_FAMILY,
    LAZY_PRICES_FAMILY_NAME,
    LAZY_PRICES_HOLDING_DAYS,
    LAZY_PRICES_LEG_WEIGHTINGS,
    LAZY_PRICES_MAX_STALENESS_DAYS,
    LAZY_PRICES_METRICS,
    LAZY_PRICES_N_TRIALS,
    LAZY_PRICES_RANK_FRACTION,
    LAZY_PRICES_SCOPES,
    STOPWORDS,
    build_inverse_vol_basis,
    build_similarity_observations,
    build_similarity_panel,
    cosine_similarity,
    jaccard_similarity,
    pair_same_type_filings,
    run_lazy_prices_screening,
    scope_text,
    screen_lazy_prices_family,
    signal_lazy_prices,
    similarity,
    term_counts,
    tokenize,
)
from app.services.research_lab.cross_sectional_quality import FactorObservation
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

# --- shared synthetic fixtures ---------------------------------------------


def _frame(values_by_ticker: dict[str, list[float]], start: str = "2018-01-01") -> pd.DataFrame:
    n = len(next(iter(values_by_ticker.values())))
    return pd.DataFrame(values_by_ticker, index=pd.bdate_range(start, periods=n))


def _filing(
    accession: str,
    form: str = "10-K",
    filing_date: date = date(2024, 2, 1),
    acceptance: str = "",
    report_date: date | None = None,
) -> FilingRef:
    return FilingRef(
        cik=1,
        accession=accession,
        form=form,
        filing_date=filing_date,
        acceptance_utc=acceptance,
        report_date=report_date,
        primary_document=f"{accession}.htm",
    )


class _StubTextProvider:
    """Returns canned text per accession and counts fetches, so memoization and
    failure handling are observable without any network."""

    def __init__(self, texts: dict[str, str], fail: set[str] | None = None):
        self.texts = texts
        self.fail = fail or set()
        self.calls: list[str] = []

    def get_filing_text(self, filing: FilingRef) -> str:
        self.calls.append(filing.accession)
        if filing.accession in self.fail:
            raise RuntimeError("simulated fetch failure")
        return self.texts[filing.accession]


BOILERPLATE = (
    "This annual report contains forward looking statements within the meaning of the "
    "Private Securities Litigation Reform Act. Such statements involve known and unknown "
    "risks uncertainties and other factors which may cause actual results to differ "
    "materially from any future results expressed or implied by such forward looking "
    "statements. The company undertakes no obligation to publicly update or revise any "
    "forward looking statements whether as a result of new information future events or "
    "otherwise except as required by applicable securities law and regulation. "
) * 12


def _section_doc(body: str, heading: str = "Item 1A. Risk Factors") -> str:
    """A document whose named section holds `body`, padded so the section is a
    realistic minority of the whole (real filings: 10-33%)."""
    pad = "unrelated filing narrative content " * 500
    return (
        f"{pad}\n{heading}\n{body}\nItem 1B. Unresolved Staff Comments\n{pad}"
    )


# --- family shape: exactly these 36, no more, no fewer ----------------------


def test_family_has_exactly_the_pre_declared_thirty_six_specs():
    assert LAZY_PRICES_N_TRIALS == 36
    assert len(LAZY_PRICES_FAMILY) == 36


def test_family_size_assertion_is_hard_not_documented():
    """The grid is frozen in the pre-registration and is the DSR denominator
    for every future run; a size drift must be a loud import-time failure."""
    assert (
        len(LAZY_PRICES_METRICS)
        * len(LAZY_PRICES_SCOPES)
        * len(LAZY_PRICES_HOLDING_DAYS)
        * len(LAZY_PRICES_LEG_WEIGHTINGS)
        == LAZY_PRICES_N_TRIALS
    )


def test_every_pattern_id_is_unique():
    ids = [s.spec.pattern_id for s in LAZY_PRICES_FAMILY]
    assert len(set(ids)) == len(ids)


def test_the_grid_covers_every_axis_value_exactly():
    assert {s.metric for s in LAZY_PRICES_FAMILY} == set(LAZY_PRICES_METRICS)
    assert {s.scope for s in LAZY_PRICES_FAMILY} == set(LAZY_PRICES_SCOPES)
    assert {s.spec.holding_days for s in LAZY_PRICES_FAMILY} == set(LAZY_PRICES_HOLDING_DAYS)
    assert {s.spec.leg_weighting for s in LAZY_PRICES_FAMILY} == set(LAZY_PRICES_LEG_WEIGHTINGS)


def test_rank_fraction_and_portfolio_are_fixed_not_searched():
    """Widening a fixed constant into an axis after seeing results is exactly
    the search the DSR machinery exists to punish."""
    assert all(s.spec.rank_fraction == LAZY_PRICES_RANK_FRACTION for s in LAZY_PRICES_FAMILY)
    assert all(s.spec.portfolio == "long_short" for s in LAZY_PRICES_FAMILY)
    assert LAZY_PRICES_RANK_FRACTION == 0.20


def test_every_spec_declares_the_family_name_and_citation():
    assert all(s.spec.family == LAZY_PRICES_FAMILY_NAME for s in LAZY_PRICES_FAMILY)
    assert all(s.spec.citation == LAZY_PRICES_CITATION for s in LAZY_PRICES_FAMILY)
    assert "Cohen, Malloy & Nguyen" in LAZY_PRICES_CITATION


def test_every_spec_requires_the_fundamental_signal_frame():
    assert all(s.spec.requires_fundamental_signal for s in LAZY_PRICES_FAMILY)


def test_family_size_clears_the_dsr_floor():
    from app.services.research_lab.deflated_sharpe import MIN_TRIALS_FOR_DSR

    assert LAZY_PRICES_N_TRIALS >= MIN_TRIALS_FOR_DSR


# --- tokenization -----------------------------------------------------------


def test_tokenizer_lowercases_and_keeps_only_letter_runs():
    assert tokenize("Revenue GREW Sharply") == ["revenue", "grew", "sharply"]


def test_tokenizer_drops_every_digit_so_numeric_churn_is_not_language_change():
    """Every filing's figures change every year mechanically; the hypothesis is
    about LANGUAGE, so numeric churn must not register as language change."""
    tokens = tokenize("Revenue of $1,234.5 million in 2025 rose 12% from FY2024")
    assert not any(any(ch.isdigit() for ch in t) for t in tokens)
    assert "revenue" in tokens and "million" in tokens and "rose" in tokens


def test_a_mixed_alphanumeric_is_split_not_discarded_and_that_is_stable():
    """Documents the exact behaviour of the frozen [a-z]{2,} definition, which
    an earlier version of this test got wrong. 'FY2024' yields 'fy', not
    nothing — and because the NEXT year's filing also yields 'fy', the residue
    is a constant across the pair rather than spurious change, while the digits
    that genuinely differ are gone."""
    assert tokenize("FY2024") == ["fy"]
    assert tokenize("FY2024") == tokenize("FY2025")
    assert tokenize("COVID-19") == ["covid"]


def test_tokenizer_removes_stopwords():
    assert "the" not in tokenize("the company and the board")
    assert tokenize("the company and the board") == ["company", "board"]


def test_single_letter_tokens_are_dropped():
    assert tokenize("a b company") == ["company"]


def test_stopword_list_covers_the_common_filing_function_words():
    for word in ("the", "of", "and", "to", "in", "that", "for", "with"):
        assert word in STOPWORDS


def test_term_counts_counts_repeats():
    assert term_counts("risk risk litigation")["risk"] == 2


# --- similarity metrics -----------------------------------------------------


def test_identical_documents_score_one_on_both_metrics():
    a = term_counts("the company faces significant litigation risk in europe")
    b = term_counts("the company faces significant litigation risk in europe")
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    assert jaccard_similarity(a, b) == pytest.approx(1.0)


def test_disjoint_documents_score_zero_on_both_metrics():
    a = term_counts("litigation risk europe")
    b = term_counts("revenue growth segments")
    assert cosine_similarity(a, b) == pytest.approx(0.0)
    assert jaccard_similarity(a, b) == pytest.approx(0.0)


def test_a_partially_changed_document_scores_between_the_extremes():
    a = term_counts("alpha beta gamma delta")
    b = term_counts("alpha beta gamma epsilon")
    for value in (cosine_similarity(a, b), jaccard_similarity(a, b)):
        assert 0.0 < value < 1.0


def test_jaccard_ignores_term_frequency_but_cosine_does_not():
    """The two metrics are genuinely different measurements, which is why
    [CMN20] reports both and why both are family axes."""
    a = Counter({"risk": 1, "growth": 1})
    b = Counter({"risk": 50, "growth": 1})
    assert jaccard_similarity(a, b) == pytest.approx(1.0)
    assert cosine_similarity(a, b) < 0.95


def test_an_empty_document_yields_nan_not_zero_similarity():
    """NaN means 'no observation' and refuses the ticker from ranking. Scoring
    an unparseable filing as 0.0 would call it maximally CHANGED and put every
    parse failure straight into the short leg."""
    assert np.isnan(cosine_similarity(Counter(), term_counts("risk")))
    assert np.isnan(jaccard_similarity(term_counts("risk"), Counter()))


def test_similarity_dispatches_on_the_declared_metric_names():
    a, b = term_counts("alpha beta"), term_counts("alpha gamma")
    assert similarity(a, b, "cosine") == pytest.approx(cosine_similarity(a, b))
    assert similarity(a, b, "jaccard") == pytest.approx(jaccard_similarity(a, b))


def test_an_unknown_metric_raises_rather_than_silently_defaulting():
    with pytest.raises(ValueError, match="unknown similarity metric"):
        similarity(term_counts("a"), term_counts("b"), "minedit")


def test_similarity_is_symmetric():
    a, b = term_counts("alpha beta gamma"), term_counts("alpha delta")
    assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))
    assert jaccard_similarity(a, b) == pytest.approx(jaccard_similarity(b, a))


# --- boilerplate dilution: the measured problem -----------------------------


def test_shared_boilerplate_compresses_similarity_toward_one():
    """The failure the brief warned about, reproduced on synthetic text: two
    documents with completely different bodies still score high when they share
    a large identical legal preamble. Measured on real filings, whole-document
    cosine sat at 0.9965-0.9998 for exactly this reason."""
    bare_a = term_counts("litigation europe antitrust investigation")
    bare_b = term_counts("revenue growth cloud segment expansion")
    with_a = term_counts(BOILERPLATE + " litigation europe antitrust investigation")
    with_b = term_counts(BOILERPLATE + " revenue growth cloud segment expansion")
    assert cosine_similarity(bare_a, bare_b) < 0.1
    assert cosine_similarity(with_a, with_b) > 0.9


def test_the_ordering_survives_boilerplate_even_though_the_level_does_not():
    """Why the family is still viable: it ranks CROSS-SECTIONALLY, so a
    compressed level is tolerable as long as a more-changed pair still scores
    below a less-changed one."""
    changed = term_counts(BOILERPLATE + " revenue growth cloud segment expansion")
    unchanged = term_counts(BOILERPLATE + " litigation europe antitrust investigation slight")
    base = term_counts(BOILERPLATE + " litigation europe antitrust investigation")
    assert cosine_similarity(base, unchanged) > cosine_similarity(base, changed)


def test_stopword_removal_widens_the_similarity_spread():
    """The measured reason stopword removal is part of the frozen tokenization:
    on 20 real consecutive 10-K pairs it widened the cosine spread ~11x."""
    raw_a = "the company and the board of the firm reported litigation in europe"
    raw_b = "the company and the board of the firm reported revenue in america"
    keep_stopwords = re_counter(raw_a), re_counter(raw_b)
    drop_stopwords = term_counts(raw_a), term_counts(raw_b)
    assert cosine_similarity(*keep_stopwords) > cosine_similarity(*drop_stopwords)


def re_counter(text: str) -> Counter:
    """Tokenize WITHOUT stopword removal — the comparison baseline for the test
    above, deliberately local to the test module so the production tokenizer
    keeps exactly one behaviour."""
    import re

    return Counter(re.findall(r"[a-z]{2,}", text.lower()))


# --- same-type pairing: a pre-registered fake-result guard ------------------


def test_a_ten_k_is_never_paired_with_a_ten_q():
    """PRE-REGISTERED FAKE-RESULT GUARD #2. An annual report and a quarterly
    report differ enormously in length and content for reasons that have
    nothing to do with news, so a cross-type pair would score a huge spurious
    'language change' correlated with the filing calendar. Deliberately mixed
    input is where this test has teeth."""
    filings = [
        _filing("k1", "10-K", date(2023, 2, 1)),
        _filing("q1", "10-Q", date(2023, 5, 1)),
        _filing("q2", "10-Q", date(2023, 8, 1)),
        _filing("k2", "10-K", date(2024, 2, 1)),
    ]
    pairs = pair_same_type_filings(filings)
    for previous, current in pairs:
        assert previous.form == current.form, (
            f"cross-type pair {previous.form} -> {current.form} — this is the bug class "
            "the family's own docstring names"
        )


def test_pairs_are_the_consecutive_ones_within_each_form_sequence():
    filings = [
        _filing("k1", "10-K", date(2023, 2, 1)),
        _filing("q1", "10-Q", date(2023, 5, 1)),
        _filing("q2", "10-Q", date(2023, 8, 1)),
        _filing("k2", "10-K", date(2024, 2, 1)),
    ]
    got = {(p.accession, c.accession) for p, c in pair_same_type_filings(filings)}
    assert got == {("q1", "q2"), ("k1", "k2")}


def test_the_first_filing_of_a_type_yields_no_pair():
    """There is nothing for it to have changed from."""
    assert pair_same_type_filings([_filing("k1")]) == []


def test_pairing_is_ordered_by_filing_date_not_input_order():
    filings = [
        _filing("k3", "10-K", date(2025, 2, 1)),
        _filing("k1", "10-K", date(2023, 2, 1)),
        _filing("k2", "10-K", date(2024, 2, 1)),
    ]
    assert [(p.accession, c.accession) for p, c in pair_same_type_filings(filings)] == [
        ("k1", "k2"),
        ("k2", "k3"),
    ]


def test_pairs_are_returned_in_current_filing_date_order():
    filings = [
        _filing("k1", "10-K", date(2023, 2, 1)),
        _filing("k2", "10-K", date(2024, 2, 1)),
        _filing("q1", "10-Q", date(2023, 5, 1)),
        _filing("q2", "10-Q", date(2023, 8, 1)),
    ]
    dates = [c.filing_date for _p, c in pair_same_type_filings(filings)]
    assert dates == sorted(dates)


def test_an_empty_filing_list_pairs_to_nothing():
    assert pair_same_type_filings([]) == []


# --- scope selection --------------------------------------------------------


def test_full_scope_returns_the_whole_document():
    assert scope_text("whole document text", "full") == "whole document text"


def test_section_scope_returns_only_the_section_body():
    body = "risk narrative content " * 100
    section = scope_text(_section_doc(body), "risk_factors")
    assert section is not None
    assert "risk narrative" in section
    assert "unrelated filing narrative" not in section


def test_a_missing_section_returns_none_so_the_filing_is_refused():
    assert scope_text("a document with no recognizable headings", "risk_factors") is None


def test_an_unknown_scope_raises():
    with pytest.raises(ValueError, match="unknown scope"):
        scope_text("text", "executive_team")


# --- observation building ---------------------------------------------------


def _two_filings() -> list[FilingRef]:
    return [
        _filing("k1", "10-K", date(2023, 2, 1), acceptance="2023-02-01T12:00:00.000Z"),
        _filing("k2", "10-K", date(2024, 2, 1), acceptance="2024-02-01T12:00:00.000Z"),
    ]


def test_observations_are_dated_by_availability_not_by_the_period_end():
    """PRE-REGISTERED FAKE-RESULT GUARD #1. Keying to the fiscal period end
    would grant a median 53-day look-ahead (measured on 481 real filings)."""
    filings = [
        _filing(
            "k1", "10-K", date(2023, 2, 1),
            acceptance="2023-02-01T12:00:00.000Z", report_date=date(2022, 12, 31),
        ),
        _filing(
            "k2", "10-K", date(2024, 2, 1),
            acceptance="2024-02-01T12:00:00.000Z", report_date=date(2023, 12, 31),
        ),
    ]
    provider = _StubTextProvider({"k1": "alpha beta gamma", "k2": "alpha beta delta"})
    observations, _ = build_similarity_observations(
        provider, {"AAA": filings}, metrics=("cosine",), scopes=("full",)
    )
    obs = observations[("cosine", "full")]["AAA"]
    assert len(obs) == 1
    assert obs[0].available == date(2024, 2, 1)
    assert obs[0].available > date(2023, 12, 31), "must not be visible at the period end"


def test_each_filing_is_fetched_once_even_though_it_joins_two_pairs():
    filings = [
        _filing("k1", "10-K", date(2022, 2, 1)),
        _filing("k2", "10-K", date(2023, 2, 1)),
        _filing("k3", "10-K", date(2024, 2, 1)),
    ]
    provider = _StubTextProvider({"k1": "a b c", "k2": "a b d", "k3": "a b e"})
    build_similarity_observations(
        provider, {"AAA": filings}, metrics=("cosine",), scopes=("full",)
    )
    assert sorted(set(provider.calls)) == ["k1", "k2", "k3"]
    assert len(provider.calls) == len(set(provider.calls))


def test_a_text_fetch_failure_is_counted_and_does_not_abort_the_run():
    filings = _two_filings()
    provider = _StubTextProvider({"k1": "a b c", "k2": "a b d"}, fail={"k2"})
    observations, report = build_similarity_observations(
        provider, {"AAA": filings}, metrics=("cosine",), scopes=("full",)
    )
    assert report.n_text_fetch_failures == 1
    assert observations[("cosine", "full")].get("AAA") in (None, [])


def test_a_missing_section_is_counted_per_scope_and_drops_only_that_scope():
    """Section coverage is NOT random across filers, so it must be reported
    rather than assumed — the full-document scope keeps the observation the
    section scope loses."""
    filings = _two_filings()
    body = "risk narrative content " * 100
    provider = _StubTextProvider(
        {"k1": _section_doc(body), "k2": "a document with no recognizable headings at all"}
    )
    _observations, report = build_similarity_observations(
        provider, {"AAA": filings}, metrics=("cosine",), scopes=("full", "risk_factors")
    )
    assert report.n_pairs_section_missing["risk_factors"] == 1
    assert report.n_pairs_scored["risk_factors"] == 0
    assert report.n_pairs_scored["full"] == 1


def test_both_metrics_share_one_tokenization_pass_and_both_get_observations():
    provider = _StubTextProvider({"k1": "alpha beta gamma", "k2": "alpha beta delta"})
    observations, _ = build_similarity_observations(
        provider, {"AAA": _two_filings()}, metrics=("cosine", "jaccard"), scopes=("full",)
    )
    assert len(observations[("cosine", "full")]["AAA"]) == 1
    assert len(observations[("jaccard", "full")]["AAA"]) == 1
    assert len(provider.calls) == 2  # one per filing, not one per metric


def test_the_build_report_counts_filings_and_pairs():
    provider = _StubTextProvider({"k1": "a b c", "k2": "a b d"})
    _obs, report = build_similarity_observations(
        provider, {"AAA": _two_filings()}, metrics=("cosine",), scopes=("full",)
    )
    assert report.n_tickers == 1
    assert report.n_filings == 2
    assert report.n_pairs == 1


# --- the point-in-time panel: a pre-registered fake-result guard -----------


def _panel_close(n: int = 400) -> pd.DataFrame:
    return _frame({"AAA": [100.0] * n, "BBB": [100.0] * n}, start="2023-01-02")


def test_a_similarity_is_nan_before_its_filing_was_available():
    """PRE-REGISTERED FAKE-RESULT GUARD #1, at the panel level. The value must
    be invisible on every row before its availability date and visible from it
    onward — forward-fill only, never backfill."""
    close = _panel_close()
    observations = {
        "AAA": [FactorObservation(end=date(2023, 12, 31), value=0.9, available=date(2024, 2, 1))]
    }
    panel, _ages, _unusable = build_similarity_panel(close, observations)
    before = panel.loc[panel.index < pd.Timestamp("2024-02-01"), "AAA"]
    on_and_after = panel.loc[panel.index >= pd.Timestamp("2024-02-01"), "AAA"]
    assert before.isna().all(), "no value may exist before the filing was accepted"
    assert on_and_after.iloc[0] == pytest.approx(0.9)


def test_the_value_is_carried_forward_but_never_interpolated():
    close = _panel_close()
    observations = {
        "AAA": [FactorObservation(end=date(2023, 12, 31), value=0.9, available=date(2024, 2, 1))]
    }
    panel, _ages, _ = build_similarity_panel(close, observations)
    held = panel.loc[panel.index >= pd.Timestamp("2024-02-01"), "AAA"].dropna()
    assert set(held.unique()) == {0.9}


def test_a_value_older_than_the_staleness_bound_goes_nan():
    """A firm whose next 10-K never arrives has stopped filing on schedule;
    carrying a year-old similarity as 'current' would be a dead-series
    masquerade."""
    close = _frame({"AAA": [100.0] * 900}, start="2023-01-02")
    observations = {
        "AAA": [FactorObservation(end=date(2022, 12, 31), value=0.9, available=date(2023, 1, 3))]
    }
    panel, ages, _ = build_similarity_panel(close, observations)
    stale = panel["AAA"].loc[
        ages["AAA"].isna() & (panel.index > pd.Timestamp("2023-01-03"))
    ]
    assert stale.isna().all()
    assert LAZY_PRICES_MAX_STALENESS_DAYS == 455


def test_a_ticker_with_no_observations_is_reported_unusable():
    close = _panel_close()
    panel, _ages, unusable = build_similarity_panel(close, {"AAA": []})
    assert "AAA" in unusable and "BBB" in unusable
    assert panel["AAA"].isna().all()


def test_the_panel_is_aligned_to_the_price_frames_index_and_columns():
    close = _panel_close()
    panel, ages, _ = build_similarity_panel(close, {"AAA": []})
    assert list(panel.columns) == list(close.columns)
    assert panel.index.equals(close.index)
    assert ages.index.equals(close.index)


def test_a_later_filing_supersedes_an_earlier_one():
    close = _panel_close()
    observations = {
        "AAA": [
            FactorObservation(end=date(2022, 12, 31), value=0.5, available=date(2023, 2, 1)),
            FactorObservation(end=date(2023, 12, 31), value=0.9, available=date(2024, 2, 1)),
        ]
    }
    panel, _ages, _ = build_similarity_panel(close, observations)
    assert panel["AAA"].loc[pd.Timestamp("2023-06-01")] == pytest.approx(0.5)
    assert panel["AAA"].loc[pd.Timestamp("2024-06-03")] == pytest.approx(0.9)


# --- the signal -------------------------------------------------------------


def test_the_signal_reads_the_last_row_of_the_truncated_history_view():
    close = _frame({"AAA": [100.0] * 5, "BBB": [100.0] * 5})
    panel = pd.DataFrame({"AAA": [0.1, 0.2, 0.3, 0.4, 0.5], "BBB": [0.9] * 5}, index=close.index)
    signal = signal_lazy_prices(CrossSectionalData(close=close, fundamental_signal=panel))
    assert signal["AAA"] == pytest.approx(0.5)
    assert signal["BBB"] == pytest.approx(0.9)


def test_high_similarity_ranks_above_low_similarity():
    """Sign convention: the harness ranks top-of-signal LONG, and high
    similarity means a NON-CHANGER, which is [CMN20]'s own long side. No flip
    is applied and the direction is not an axis."""
    close = _frame({"CHANGER": [100.0] * 3, "NONCHANGER": [100.0] * 3})
    panel = pd.DataFrame(
        {"CHANGER": [0.70] * 3, "NONCHANGER": [0.99] * 3}, index=close.index
    )
    signal = signal_lazy_prices(CrossSectionalData(close=close, fundamental_signal=panel))
    assert signal["NONCHANGER"] > signal["CHANGER"]


def test_the_signal_refuses_to_run_without_a_panel():
    close = _frame({"AAA": [100.0] * 3})
    with pytest.raises(ValueError, match="requires CrossSectionalData.fundamental_signal"):
        signal_lazy_prices(CrossSectionalData(close=close))


def test_non_finite_cells_are_passed_through_as_nan_and_refuse_the_ticker():
    close = _frame({"AAA": [100.0] * 3, "BBB": [100.0] * 3})
    panel = pd.DataFrame(
        {"AAA": [np.nan] * 3, "BBB": [np.inf] * 3}, index=close.index
    )
    signal = signal_lazy_prices(CrossSectionalData(close=close, fundamental_signal=panel))
    assert signal.isna().all()


# --- inverse-vol basis ------------------------------------------------------


def test_inverse_vol_basis_is_higher_for_the_calmer_ticker():
    rng = np.random.default_rng(11)
    n = 200
    calm = list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.004, n)))
    wild = list(100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.030, n)))
    basis = build_inverse_vol_basis(_frame({"CALM": calm, "WILD": wild}))
    assert basis["CALM"].iloc[-1] > basis["WILD"].iloc[-1]


def test_inverse_vol_basis_is_nan_before_the_minimum_window():
    basis = build_inverse_vol_basis(_frame({"AAA": [100.0 + i for i in range(60)]}))
    assert basis["AAA"].iloc[0:39].isna().all()


# --- screening / DSR --------------------------------------------------------


def _screening_fixture(n_tickers: int = 30, n_days: int = 700, seed: int = 7):
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    close = _frame(
        {t: list(100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.015, n_days))) for t in tickers},
        start="2020-01-01",
    )
    panels = {}
    for metric in LAZY_PRICES_METRICS:
        for scope in LAZY_PRICES_SCOPES:
            values = rng.uniform(0.90, 0.999, size=(n_days, n_tickers))
            panels[(metric, scope)] = pd.DataFrame(values, index=close.index, columns=tickers)
    return close, panels, tickers


def test_screening_produces_a_result_per_spec_with_a_pooled_dsr():
    close, panels, tickers = _screening_fixture()
    config = CrossSectionalConfig(formation_start=date(2020, 6, 1))
    results = screen_lazy_prices_family(
        close,
        panels,
        config,
        leg_weight_basis=build_inverse_vol_basis(close),
        membership_fn=fixed_universe_membership(tickers),
    )
    assert results, "the synthetic fixture should replay every spec"
    assert all(r.deflated_sharpe.n_trials == LAZY_PRICES_N_TRIALS for r in results)
    assert all(r.family == LAZY_PRICES_FAMILY_NAME for r in results)


def test_n_trials_is_the_pre_declared_thirty_six_not_the_survivor_count():
    """Shrinking the denominator to however many specs cleared the data floors
    would be gameable by defining specs expected to fail."""
    close, panels, tickers = _screening_fixture()
    config = CrossSectionalConfig(formation_start=date(2020, 6, 1))
    subset = [s for s in LAZY_PRICES_FAMILY if s.metric == "cosine" and s.scope == "full"]
    results = screen_lazy_prices_family(
        close,
        panels,
        config,
        specs=subset,
        leg_weight_basis=build_inverse_vol_basis(close),
        membership_fn=fixed_universe_membership(tickers),
    )
    assert results
    assert all(r.deflated_sharpe.n_trials == LAZY_PRICES_N_TRIALS for r in results)


def test_a_smaller_n_trials_than_the_specs_screened_is_refused():
    """Trial-count laundering — reporting a DSR corrected for fewer comparisons
    than were really made. This project has identified and rejected it before."""
    close, panels, tickers = _screening_fixture()
    with pytest.raises(ValueError, match="trial-count laundering"):
        screen_lazy_prices_family(
            close,
            panels,
            CrossSectionalConfig(formation_start=date(2020, 6, 1)),
            membership_fn=fixed_universe_membership(tickers),
            n_trials=2,
        )


def test_sigma_sr_is_pooled_across_panels_not_estimated_within_one():
    """The reason this module runs its own screening loop. Six specs sharing a
    panel differ only in hold and weighting, so their Sharpe dispersion
    understates the full family's — and a smaller sigma_sr makes every DSR
    EASIER, the anti-conservative direction."""
    close, panels, tickers = _screening_fixture()
    config = CrossSectionalConfig(formation_start=date(2020, 6, 1))
    membership = fixed_universe_membership(tickers)
    basis = build_inverse_vol_basis(close)
    pooled = screen_lazy_prices_family(
        close, panels, config, leg_weight_basis=basis, membership_fn=membership
    )
    one_panel = screen_lazy_prices_family(
        close,
        panels,
        config,
        specs=[s for s in LAZY_PRICES_FAMILY if s.metric == "cosine" and s.scope == "full"],
        leg_weight_basis=basis,
        membership_fn=membership,
    )
    pooled_sigma = {r.deflated_sharpe.sigma_sr_annualized for r in pooled}
    single_sigma = {r.deflated_sharpe.sigma_sr_annualized for r in one_panel}
    assert len(pooled_sigma) == 1 and len(single_sigma) == 1
    assert pooled_sigma != single_sigma


def test_results_are_sorted_by_sharpe_descending():
    close, panels, tickers = _screening_fixture()
    results = screen_lazy_prices_family(
        close,
        panels,
        CrossSectionalConfig(formation_start=date(2020, 6, 1)),
        leg_weight_basis=build_inverse_vol_basis(close),
        membership_fn=fixed_universe_membership(tickers),
    )
    sharpes = [r.sharpe_annualized for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_a_spec_whose_panel_is_absent_is_skipped_rather_than_crashing():
    close, panels, tickers = _screening_fixture()
    del panels[("cosine", "full")]
    results = screen_lazy_prices_family(
        close,
        panels,
        CrossSectionalConfig(formation_start=date(2020, 6, 1)),
        leg_weight_basis=build_inverse_vol_basis(close),
        membership_fn=fixed_universe_membership(tickers),
    )
    assert all("cosine_full" not in r.pattern_id for r in results)


# --- production entry point guard -------------------------------------------


def test_screening_before_membership_coverage_is_refused_loudly():
    """was_member answers a silent False for every date before coverage, so a
    run starting earlier would rank an empty universe and report it as a
    finding rather than as a configuration error."""
    with pytest.raises(ValueError, match="predates point-in-time membership coverage"):
        run_lazy_prices_screening(
            date(2010, 1, 4), date(2020, 1, 1), tickers=["AAA"]
        )


def test_membership_data_start_is_the_declared_floor():
    assert MEMBERSHIP_DATA_START == date(2015, 1, 7)
