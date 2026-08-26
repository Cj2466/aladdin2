from app.config import Settings


def test_api_key_fields_strip_surrounding_whitespace():
    """Regression test: a trailing newline on FINNHUB_API_KEY (from how it
    was pasted into Render's environment-variable UI) made every Finnhub
    call fail with a 401, since httpx sent the newline as part of the
    token. Reproduced directly against production and confirmed via the
    literal '%0A' at the end of the failing request URL."""
    settings = Settings(
        finnhub_api_key="abc123\n",
        fred_api_key="  def456  ",
        resend_api_key="\tghi789\n",
        alpaca_api_key="  jkl012\n",
        alpaca_api_secret="\tmno345  ",
    )
    assert settings.finnhub_api_key == "abc123"
    assert settings.fred_api_key == "def456"
    assert settings.resend_api_key == "ghi789"
    assert settings.alpaca_api_key == "jkl012"
    assert settings.alpaca_api_secret == "mno345"


def test_alpaca_settings_default_to_empty_credentials_and_paper_mode():
    """Fresh checkouts without an .env must default to no credentials (the
    provider then refuses to make any network call) and paper mode — live
    trading must never be a silent default, even though nothing reads the
    paper flag for execution yet (Phase B is market-data-only)."""
    settings = Settings(_env_file=None)
    assert settings.alpaca_api_key == ""
    assert settings.alpaca_api_secret == ""
    assert settings.alpaca_paper_trading is True
