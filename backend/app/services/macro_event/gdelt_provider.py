"""GDELT DOC 2.0 API client — world-news volume/tone monitoring for
"Project 2" Stage A.

Free, keyless, and purpose-built for real-time news monitoring across 100+
languages. This is the world-news complement to sec_edgar_rss_provider's
company-specific filing view.

ENDPOINT — https://api.gdeltproject.org/api/v2/doc/doc
Probed LIVE 2026-09-01/02. Everything below is what the real service actually
did, not what its documentation suggests.

THE VERIFIED RESPONSE SHAPE (mode=timelinevol, format=json), captured live:

    {"query_details": {"title": "oil sourcelang:eng", "date_resolution": "15m"},
     "timeline": [
       {"series": "Volume Intensity",
        "data": [{"date": "20260831T181500Z", "value": 1.9942},
                 {"date": "20260831T183000Z", "value": 1.2605},
                 {"date": "20260831T190000Z", "value": 2.761}, ...]}]}

Four things in that payload changed the code below:

1. `date` IS COMPACT ISO 8601 BASIC FORMAT — "20260831T181500Z", with no
   dashes or colons. datetime.fromisoformat does NOT accept it on the Python
   this project targets, so it is parsed with an explicit strptime format.

2. `value` FROM timelinevol IS NOT AN ARTICLE COUNT. GDELT labels the series
   "Volume Intensity", and it is the PERCENTAGE OF ALL ARTICLES GDELT
   monitored in that bucket which matched the query (observed values ~1.3-2.8
   for a broad oil query). It is already normalised against total news volume,
   which is a genuinely better input to a spike detector than a raw count —
   a raw count rises on any busy news day — but it means the number must never
   be described or logged as "articles".

3. BUCKETS ARE IRREGULAR AND SPARSE. The live series ran 1815, 1830, 1900,
   1915, 1930, 2000, 2045, 2100, 2200, 2230 — GDELT omits buckets rather than
   emitting zeros, so consecutive entries are NOT evenly spaced. Nothing here
   may assume a fixed cadence or index by position-as-time.

4. `query_details.date_resolution` was "15m" for a 24h timespan.

THE PLAN ASKED FOR A 15-MINUTE WINDOW; GDELT REFUSES ONE
============================================================================
`timespan=15min` returns **HTTP 200** with Content-Type `text/html` and the
body `Timespan is too short.` — a 23-byte plain-text refusal wearing a success
status code. A client that called .raise_for_status() would sail straight past
it and a client that called .json() would crash.

The resolution is better than the original ask rather than a compromise: a 24h
timespan returns 15-MINUTE BUCKETS, so the newest bucket IS the rolling
15-minute window the plan wanted, and the preceding buckets supply the trailing
baseline that a volume z-score or a tone shift REQUIRES. The plan's literal
15-minute window could not have produced a z-score at all — there would have
been exactly one observation and nothing to compare it against.

OTHER MEASURED BEHAVIOUR THE CLIENT HAS TO SURVIVE
============================================================================
* RATE LIMITING IS PLAIN TEXT, NOT JSON. A too-fast request returns HTTP 429
  with the body "Please limit requests to one every 5 seconds or contact
  <address> for larger queries..." — observed repeatedly.
* THE STATED 5-SECOND LIMIT IS NOT THE WHOLE STORY. 429s were observed even at
  15-second spacing, so GDELT_MIN_SECONDS_BETWEEN_REQUESTS below is set well
  above the published figure rather than at it.
* THE SERVICE IS SLOW AND FLAKY FROM A RESIDENTIAL CONNECTION. Measured TLS
  handshakes of 18-21 SECONDS, plus frequent ECONNRESET and connect timeouts.
  Hence the long default timeout, and hence a SINGLE REUSED httpx.Client on
  the provider instance: HTTP keep-alive amortises that handshake across a
  tick's several theme queries instead of paying it once per query.

Because of all of the above, EVERY FAILURE MODE HERE IS EXPECTED RATHER THAN
EXCEPTIONAL, and the scanner treats a GDELT outage as a recorded non-answer
for that theme, never as a reason to lose the tick.
"""

import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's own 429 body asks for one request every 5 seconds. 429s were still
# observed at 15s spacing from this network, so this is deliberately well above
# the published number — a shared free public service, and the scanner has a
# 300-second tick to spend.
GDELT_MIN_SECONDS_BETWEEN_REQUESTS = 6.0

# Measured TLS handshakes of 18-21s from a residential connection, before any
# response body. A short timeout here would fail every request on a slow day.
GDELT_TIMEOUT_SECONDS = 90.0

# Same exponential-backoff-with-jitter shape as
# yfinance_provider._call_with_retry, this project's retry precedent.
GDELT_RETRY_ATTEMPTS = 3
GDELT_RETRY_BASE_DELAY_SECONDS = 2.0

# 24h at GDELT's 15-minute resolution. The newest bucket is the "rolling
# 15-minute window" the plan asked for; the rest are the baseline that makes a
# z-score computable at all. NOT "15min", which GDELT refuses outright.
GDELT_DEFAULT_TIMESPAN = "24h"

# A z-score needs a baseline. With sparse, irregular buckets (see the module
# docstring) a 24h window typically yields dozens, but a quiet query can yield
# very few, and a z-score over 3 points is noise dressed as a statistic.
GDELT_MIN_BASELINE_BUCKETS = 8

MODE_TIMELINE_VOLUME = "timelinevol"
MODE_TIMELINE_TONE = "timelinetone"

# GDELT's compact ISO 8601 basic format: "20260831T181500Z".
_GDELT_DATE_FORMAT = "%Y%m%dT%H%M%SZ"


class GdeltError(RuntimeError):
    """A GDELT query did not produce a trustworthy answer.

    Raised for transport failures, rate limiting, and — importantly — for an
    HTTP 200 carrying a non-JSON body, which is how GDELT reports several real
    errors (see the module docstring). It is NOT raised for a query that
    legitimately matched little or nothing; that returns a result with
    `n_buckets` low and `zscore`/`tone_shift` None, which the scanner records
    as an honest non-answer.
    """


@dataclass(frozen=True)
class GdeltBucket:
    at: datetime
    value: float


@dataclass(frozen=True)
class GdeltSeriesSignal:
    """One theme's measurement from one GDELT mode.

    `latest` / `baseline_mean` / `baseline_std` are None when there were too
    few buckets to say anything. That is a real, common, honest state — a
    quiet theme in a 15-minute window — and it is NEVER coerced to 0.0, which
    would read as a measured "no activity" instead of "not measurable".
    """

    theme_key: str
    mode: str
    n_buckets: int
    latest: float | None
    latest_at: datetime | None
    baseline_mean: float | None
    baseline_std: float | None
    # (latest - baseline_mean) / baseline_std, for volume.
    zscore: float | None
    # latest - baseline_mean, for tone. An absolute shift, not standardised:
    # GDELT tone is already on a fixed, interpretable scale (roughly -100..+100
    # with real values almost always inside -10..+10), so an absolute move is
    # the meaningful quantity and dividing by a near-zero std would manufacture
    # enormous spurious values on a flat theme.
    shift: float | None

    def as_dict(self) -> dict:
        return {
            "theme": self.theme_key,
            "mode": self.mode,
            "n_buckets": self.n_buckets,
            "latest": self.latest,
            "latest_at": self.latest_at.isoformat() if self.latest_at else None,
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "zscore": self.zscore,
            "shift": self.shift,
        }


def parse_timeline(payload: dict) -> list[GdeltBucket]:
    """Extract the bucket series from a DOC 2.0 timeline* response.

    Handles the verified envelope: {"timeline": [{"series": ..., "data":
    [{"date": "20260831T181500Z", "value": 1.99}, ...]}]}.

    A malformed individual bucket is skipped rather than failing the series —
    the series is a spike statistic, and one unparseable point should not
    blind the scanner. A payload with no `timeline` key at all is a shape
    failure and raises, because silently returning an empty series would be
    indistinguishable from a genuinely quiet theme.
    """
    timeline = payload.get("timeline")
    if not isinstance(timeline, list):
        raise GdeltError(
            f"response had no 'timeline' array (keys: {sorted(payload)}) — "
            "refusing to read a malformed payload as a quiet theme"
        )
    if not timeline:
        return []

    data = timeline[0].get("data") if isinstance(timeline[0], dict) else None
    if not isinstance(data, list):
        raise GdeltError("response 'timeline[0]' had no 'data' array")

    buckets: list[GdeltBucket] = []
    for point in data:
        if not isinstance(point, dict):
            continue
        raw_date = point.get("date")
        raw_value = point.get("value")
        if not isinstance(raw_date, str):
            continue
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            continue
        try:
            at = datetime.strptime(raw_date, _GDELT_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            logger.warning("GDELT: unparseable bucket date %r", raw_date)
            continue
        buckets.append(GdeltBucket(at=at, value=float(raw_value)))

    # GDELT returned them in ascending order live, but sorting explicitly means
    # "the newest bucket" stays correct even if that ever changes — the whole
    # signal depends on which bucket is last.
    buckets.sort(key=lambda b: b.at)
    return buckets


def summarise(
    theme_key: str,
    mode: str,
    buckets: list[GdeltBucket],
    *,
    min_baseline: int = GDELT_MIN_BASELINE_BUCKETS,
) -> GdeltSeriesSignal:
    """Newest bucket vs. the trailing baseline of everything before it.

    Returns a signal with None statistics rather than raising when there is
    too little data. A zero standard deviation also yields None: a theme whose
    volume was literally constant across the baseline gives a z-score of
    infinity for any deviation at all, which is a division artefact and not a
    detection.
    """
    n = len(buckets)
    if n == 0:
        return GdeltSeriesSignal(theme_key, mode, 0, None, None, None, None, None, None)

    latest = buckets[-1]
    baseline = buckets[:-1]
    if len(baseline) < min_baseline:
        return GdeltSeriesSignal(
            theme_key, mode, n, latest.value, latest.at, None, None, None, None
        )

    values = [b.value for b in baseline]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = variance**0.5

    zscore = (latest.value - mean) / std if std > 0 else None
    shift = latest.value - mean

    return GdeltSeriesSignal(
        theme_key=theme_key,
        mode=mode,
        n_buckets=n,
        latest=latest.value,
        latest_at=latest.at,
        baseline_mean=mean,
        baseline_std=std,
        zscore=zscore,
        shift=shift,
    )


class GdeltProvider:
    """Throttled, retrying DOC 2.0 client.

    Holds ONE httpx.Client for its lifetime so keep-alive amortises GDELT's
    18-21 second TLS handshake across a tick's several theme queries. `sleep`
    and `clock` are injectable so tests drive the throttle with no real
    waiting, matching EdgarXbrlProvider's construction.
    """

    def __init__(
        self,
        min_request_interval: float = GDELT_MIN_SECONDS_BETWEEN_REQUESTS,
        timeout: float = GDELT_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        client: httpx.Client | None = None,
    ) -> None:
        self.min_request_interval = min_request_interval
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._client = client if client is not None else httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Aladdin2 Research (macro-event scanner)"},
        )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            remaining = self.min_request_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _query(self, query: str, mode: str, timespan: str) -> dict:
        """One DOC 2.0 call, returning the parsed JSON body.

        THE CRITICAL GUARD IS THE HTTP-200-BUT-NOT-JSON CHECK. GDELT reports
        several real errors that way — "Timespan is too short." arrives as a
        200 with Content-Type text/html — so neither the status code nor a
        naive .json() is sufficient on its own.
        """
        params = {"query": query, "mode": mode, "format": "json", "timespan": timespan}
        last_error: Exception | None = None

        for attempt in range(1, GDELT_RETRY_ATTEMPTS + 1):
            self._throttle()
            try:
                response = self._client.get(GDELT_DOC_URL, params=params)
            except Exception as exc:  # noqa: BLE001 — ECONNRESET/timeouts are routine here
                last_error = exc
                logger.warning("GDELT %s attempt %d failed: %s", mode, attempt, exc)
            else:
                if response.status_code == 429:
                    # Plain text, never JSON. Back off harder than the normal
                    # retry: being told to slow down is not a transient blip.
                    last_error = GdeltError(f"rate limited: {response.text.strip()[:120]}")
                    logger.warning("GDELT %s attempt %d rate limited", mode, attempt)
                    if attempt < GDELT_RETRY_ATTEMPTS:
                        self._sleep(self.min_request_interval * 2)
                    continue
                if response.status_code != 200:
                    last_error = GdeltError(f"HTTP {response.status_code}")
                else:
                    body = response.text.strip()
                    if not body.startswith("{"):
                        # A 200 carrying plain text is a REFUSAL, not data, and
                        # retrying will not change it — "Timespan is too short."
                        # is deterministic for a given request.
                        raise GdeltError(
                            f"GDELT refused the query with a non-JSON 200: {body[:160]!r}"
                        )
                    try:
                        return json.loads(body)
                    except ValueError as exc:
                        last_error = exc

            if attempt < GDELT_RETRY_ATTEMPTS:
                self._sleep(
                    GDELT_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
                )

        raise GdeltError(f"GDELT {mode} failed after {GDELT_RETRY_ATTEMPTS} attempts") from last_error

    def fetch_series(
        self,
        theme_key: str,
        query: str,
        mode: str,
        *,
        timespan: str = GDELT_DEFAULT_TIMESPAN,
        min_baseline: int = GDELT_MIN_BASELINE_BUCKETS,
    ) -> GdeltSeriesSignal:
        """One theme, one mode -> a summarised signal. Raises GdeltError when
        the query produced no trustworthy answer at all."""
        payload = self._query(query, mode, timespan)
        return summarise(theme_key, mode, parse_timeline(payload), min_baseline=min_baseline)

    def close(self) -> None:
        self._client.close()
