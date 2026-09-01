"""Unit tests for the GDELT DOC 2.0 client.

Every fixture is a recorded-shape reproduction of what the real API returned
when probed LIVE on 2026-09-01/02 (see gdelt_provider.py's docstring for the
captured payloads, including the two plain-text refusals that arrive wearing
misleading status codes). NO TEST HERE TOUCHES THE NETWORK.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.services.macro_event.gdelt_provider import (
    MODE_TIMELINE_TONE,
    MODE_TIMELINE_VOLUME,
    GdeltBucket,
    GdeltError,
    GdeltProvider,
    parse_timeline,
    summarise,
)

# Verbatim shape of the real mode=timelinevol response (query "oil
# sourcelang:eng", timespan=24h). Note "Volume Intensity", the compact
# 20260831T181500Z dates, and the IRREGULAR spacing (1815, 1830, 1900 — GDELT
# omits empty buckets rather than emitting zeros).
LIVE_VOLUME_PAYLOAD = {
    "query_details": {"title": "oil sourcelang:eng", "date_resolution": "15m"},
    "timeline": [
        {
            "series": "Volume Intensity",
            "data": [
                {"date": "20260831T181500Z", "value": 1.9942},
                {"date": "20260831T183000Z", "value": 1.2605},
                {"date": "20260831T190000Z", "value": 2.761},
                {"date": "20260831T191500Z", "value": 2.2815},
                {"date": "20260831T193000Z", "value": 2.2001},
                {"date": "20260831T200000Z", "value": 2.307},
                {"date": "20260831T204500Z", "value": 2.7967},
                {"date": "20260831T210000Z", "value": 2.236},
                {"date": "20260831T220000Z", "value": 1.8424},
                {"date": "20260831T223000Z", "value": 2.0},
            ],
        }
    ],
}

# Verbatim shape of the real mode=timelinetone response — SAME envelope, series
# "Average Tone", values in the observed real range (live min/max over 56
# buckets: -3.7304 / +2.864).
LIVE_TONE_PAYLOAD = {
    "query_details": {"title": "oil sourcelang:eng", "date_resolution": "15m"},
    "timeline": [
        {
            "series": "Average Tone",
            "data": [
                {"date": "20260831T181500Z", "value": -2.5829},
                {"date": "20260831T183000Z", "value": 2.864},
                {"date": "20260831T190000Z", "value": -3.695},
                {"date": "20260831T191500Z", "value": -3.1171},
                {"date": "20260831T193000Z", "value": -1.8894},
                {"date": "20260831T200000Z", "value": -3.7304},
                {"date": "20260831T204500Z", "value": -2.8104},
                {"date": "20260831T210000Z", "value": -2.9764},
                {"date": "20260831T220000Z", "value": -1.9879},
                {"date": "20260901T170000Z", "value": -1.4819},
            ],
        }
    ],
}


def _provider(handler) -> GdeltProvider:
    return GdeltProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def _serving(payload=None, *, status_code=200, text=None) -> GdeltProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if text is not None:
            return httpx.Response(status_code, text=text)
        return httpx.Response(status_code, json=payload)

    return _provider(handler)


# --- parsing the real shapes ------------------------------------------------


def test_parses_the_real_volume_envelope_including_compact_dates():
    buckets = parse_timeline(LIVE_VOLUME_PAYLOAD)
    assert len(buckets) == 10
    # GDELT's compact ISO 8601 BASIC format has no dashes or colons and is not
    # accepted by datetime.fromisoformat — hence the explicit strptime format.
    assert buckets[0].at == datetime(2026, 8, 31, 18, 15, tzinfo=UTC)
    assert buckets[0].value == 1.9942
    assert buckets[-1].at == datetime(2026, 8, 31, 22, 30, tzinfo=UTC)


def test_tone_uses_the_same_envelope_as_volume():
    """Verified live: timelinevol and timelinetone differ only in the `series`
    label, so one parser serves both."""
    buckets = parse_timeline(LIVE_TONE_PAYLOAD)
    assert len(buckets) == 10
    assert buckets[0].value == -2.5829


def test_buckets_are_sorted_so_latest_is_really_the_newest():
    shuffled = {
        "timeline": [
            {
                "series": "Volume Intensity",
                "data": [
                    {"date": "20260831T190000Z", "value": 3.0},
                    {"date": "20260831T181500Z", "value": 1.0},
                ],
            }
        ]
    }
    assert [b.value for b in parse_timeline(shuffled)] == [1.0, 3.0]


def test_missing_timeline_key_raises_rather_than_reading_as_a_quiet_theme():
    """Silently returning an empty series for a malformed payload would be
    indistinguishable from a genuinely quiet theme — and a permanently dead
    trigger source that nobody can tell apart from 'nothing happened' is the
    exact failure this phase must not ship."""
    with pytest.raises(GdeltError, match="no 'timeline' array"):
        parse_timeline({"query_details": {}})


def test_an_unknown_gkg_theme_returns_an_empty_object_and_must_raise():
    """MEASURED LIVE against the real API: `theme:ZZZ_NOT_A_REAL_THEME`
    answered with an EMPTY JSON OBJECT — `{}`, no `timeline` key, HTTP 200, no
    error status and no message. GDELT does not announce an unknown theme; it
    simply returns nothing.

    This is why the shape guard is load-bearing rather than defensive
    boilerplate. Without it a misspelled theme would parse as zero buckets,
    summarise to a None signal, and register forever as 'quiet' — a silently
    dead trigger source indistinguishable from a peaceful news cycle. This
    exact payload is what the live control returned."""
    with pytest.raises(GdeltError, match="no 'timeline' array"):
        parse_timeline({})


def test_individual_malformed_buckets_are_skipped():
    payload = {
        "timeline": [
            {
                "series": "Volume Intensity",
                "data": [
                    {"date": "not-a-date", "value": 1.0},
                    {"date": "20260831T181500Z", "value": "not-a-number"},
                    {"date": "20260831T183000Z", "value": True},  # bool, not a real value
                    {"date": "20260831T190000Z", "value": 2.5},
                ],
            }
        ]
    }
    assert [b.value for b in parse_timeline(payload)] == [2.5]


# --- the statistics ---------------------------------------------------------


def _buckets(values: list[float]) -> list[GdeltBucket]:
    return [
        GdeltBucket(at=datetime(2026, 8, 31, 0, i, tzinfo=UTC), value=v)
        for i, v in enumerate(values)
    ]


def test_zscore_is_latest_against_the_trailing_baseline():
    signal = summarise("energy", MODE_TIMELINE_VOLUME, _buckets([1.0] * 9 + [5.0]), min_baseline=8)
    assert signal.n_buckets == 10
    assert signal.latest == 5.0
    assert signal.baseline_mean == 1.0
    # Baseline is perfectly flat -> std 0 -> a z-score would be infinite. That
    # is a division artefact, not a detection.
    assert signal.zscore is None


def test_zscore_computed_on_a_real_varying_baseline():
    signal = summarise(
        "energy", MODE_TIMELINE_VOLUME, _buckets([1, 2, 1, 2, 1, 2, 1, 2, 1, 10]), min_baseline=8
    )
    assert signal.zscore is not None
    assert signal.zscore > 3.0


def test_too_few_baseline_buckets_yields_none_not_zero():
    """A quiet theme is a real, common state. Coercing it to 0.0 would read as
    a measured 'no anomaly' rather than 'not measurable'."""
    signal = summarise("energy", MODE_TIMELINE_VOLUME, _buckets([1.0, 2.0]), min_baseline=8)
    assert signal.n_buckets == 2
    assert signal.latest == 2.0
    assert signal.zscore is None
    assert signal.baseline_mean is None


def test_empty_series_is_all_none():
    signal = summarise("energy", MODE_TIMELINE_VOLUME, [])
    assert signal.n_buckets == 0
    assert signal.latest is None
    assert signal.zscore is None


def test_tone_shift_is_absolute_not_standardised():
    """GDELT tone is already on a fixed interpretable scale (live values sat
    inside -3.73..+2.86), so an absolute move is the meaningful quantity;
    dividing by a near-zero std would manufacture huge spurious values."""
    signal = summarise("energy", MODE_TIMELINE_TONE, _buckets([-2.0] * 9 + [-6.0]), min_baseline=8)
    assert signal.shift == pytest.approx(-4.0)


# --- THE failure modes that wear misleading status codes -------------------


def test_http_200_with_plain_text_is_a_refusal_not_data():
    """MEASURED LIVE: `timespan=15min` returns HTTP 200, Content-Type
    text/html, body "Timespan is too short.". raise_for_status() sails past it
    and .json() crashes on it, so the body is checked explicitly.

    It also must NOT be retried — the refusal is deterministic for a given
    request, so retrying only burns rate limit."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200, text="Timespan is too short.")

    with pytest.raises(GdeltError, match="non-JSON 200"):
        _provider(handler).fetch_series("energy", "oil", MODE_TIMELINE_VOLUME)
    assert attempts["n"] == 1


def test_rate_limit_429_is_plain_text_and_is_retried_then_raised():
    """MEASURED LIVE: a too-fast request returns 429 with a plain-text body,
    never JSON — observed even at 15-second spacing."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(429, text="Please limit requests to one every 5 seconds")

    with pytest.raises(GdeltError, match="failed after"):
        _provider(handler).fetch_series("energy", "oil", MODE_TIMELINE_VOLUME)
    assert attempts["n"] == 3


def test_connection_errors_are_retried_then_raised():
    """ECONNRESET and connect timeouts were the DOMINANT observed outcome from
    a residential connection, not a rare edge case."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("Connection reset by peer")

    with pytest.raises(GdeltError, match="failed after"):
        _provider(handler).fetch_series("energy", "oil", MODE_TIMELINE_VOLUME)
    assert attempts["n"] == 3


def test_a_transient_failure_is_recovered_by_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("Connection reset by peer")
        return httpx.Response(200, json=LIVE_VOLUME_PAYLOAD)

    signal = _provider(handler).fetch_series("energy", "oil", MODE_TIMELINE_VOLUME)
    assert signal.n_buckets == 10
    assert attempts["n"] == 2


def test_request_sends_json_format_and_the_declared_query():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=LIVE_VOLUME_PAYLOAD)

    _provider(handler).fetch_series("energy", "(oil OR opec) sourcelang:eng", MODE_TIMELINE_VOLUME)
    assert seen["query"] == "(oil OR opec) sourcelang:eng"
    assert seen["mode"] == MODE_TIMELINE_VOLUME
    assert seen["format"] == "json"
    # NOT "15min", which GDELT refuses outright.
    assert seen["timespan"] == "24h"


def test_throttle_spaces_requests_apart():
    """GDELT asks for one request every 5 seconds and was observed 429ing even
    at 15s, so the client must not burst."""
    slept: list[float] = []
    clock = {"t": 0.0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LIVE_VOLUME_PAYLOAD)

    provider = GdeltProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=slept.append,
        clock=lambda: clock["t"],
        min_request_interval=6.0,
    )
    provider.fetch_series("a", "q", MODE_TIMELINE_VOLUME)
    provider.fetch_series("b", "q", MODE_TIMELINE_VOLUME)
    assert slept and slept[-1] == pytest.approx(6.0)
