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
    )
    assert settings.finnhub_api_key == "abc123"
    assert settings.fred_api_key == "def456"
    assert settings.resend_api_key == "ghi789"
