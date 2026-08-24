from app.services.research_lab.ticker_universe import SCREENING_UNIVERSE


def test_no_duplicate_tickers():
    assert len(SCREENING_UNIVERSE) == len(set(SCREENING_UNIVERSE))


def test_all_tickers_uppercase():
    assert all(t == t.upper() for t in SCREENING_UNIVERSE)


def test_universe_size_matches_documented_count():
    # Catches an accidental edit to the list going unnoticed.
    assert len(SCREENING_UNIVERSE) == 503
