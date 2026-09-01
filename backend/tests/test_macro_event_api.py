"""GET /api/macro-event/detections — the read-only Stage-A detection log.

This phase's whole API surface is one read endpoint: there is nothing to act
on, because Stage B (Phase 2.3) and the execution pathway (Phase 2.4) do not
exist yet.
"""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.macro_event_detection import MacroEventDetection
from app.schemas.macro_event import MACRO_EVENT_EVIDENCE_DISCLAIMER

BASE = datetime(2026, 9, 1, 12, 0, 0)


@pytest.fixture
def seeded(test_db_engine):
    """Three ticks x three sources = 9 rows, only some triggered."""
    session = sessionmaker(bind=test_db_engine, autoflush=False, autocommit=False)()
    try:
        for tick in range(3):
            detected_at = BASE + timedelta(minutes=5 * tick)
            for source in ("numeric", "gdelt", "edgar"):
                triggered = tick == 2 and source == "numeric"
                session.add(
                    MacroEventDetection(
                        detected_at=detected_at,
                        source=source,
                        driver="oil_uso" if triggered else None,
                        trigger_metric="daily_pct_change" if triggered else None,
                        trigger_value=0.09 if triggered else None,
                        trigger_threshold=0.04 if triggered else None,
                        triggered=triggered,
                        escalated=False,
                        raw_metrics_json=json.dumps({"tick": tick, "source": source}),
                        error=None,
                    )
                )
        session.commit()
    finally:
        session.close()


def test_requires_authentication(client):
    assert client.get("/api/macro-event/detections").status_code == 401


def test_returns_most_recent_first_with_the_disclaimer(client, register_and_verify, seeded):
    register_and_verify(client)
    body = client.get("/api/macro-event/detections").json()

    assert body["total"] == 9
    assert len(body["detections"]) == 9
    # Newest tick first.
    assert body["detections"][0]["detected_at"].startswith("2026-09-01T12:10")
    assert body["detections"][-1]["detected_at"].startswith("2026-09-01T12:00")
    # Structurally non-optional on the response contract, so no client can
    # render this data without it.
    assert body["disclaimer"] == MACRO_EVENT_EVIDENCE_DISCLAIMER
    assert "UNCALIBRATED" in body["disclaimer"]


def test_non_triggers_are_returned_by_default(client, register_and_verify, seeded):
    """The non-triggers are the denominator that makes the observed trigger
    RATE meaningful — they are the point of the table, not noise to filter."""
    register_and_verify(client)
    body = client.get("/api/macro-event/detections").json()
    assert sum(1 for d in body["detections"] if not d["triggered"]) == 8


def test_triggered_only_filter(client, register_and_verify, seeded):
    register_and_verify(client)
    body = client.get("/api/macro-event/detections?triggered_only=true").json()
    assert body["total"] == 1
    assert body["detections"][0]["driver"] == "oil_uso"
    assert body["detections"][0]["trigger_value"] == pytest.approx(0.09)
    # The threshold is snapshotted onto the row, so a later recalibration
    # never retroactively rewrites what this row meant.
    assert body["detections"][0]["trigger_threshold"] == pytest.approx(0.04)


def test_source_filter(client, register_and_verify, seeded):
    register_and_verify(client)
    body = client.get("/api/macro-event/detections?source=gdelt").json()
    assert body["total"] == 3
    assert {d["source"] for d in body["detections"]} == {"gdelt"}


def test_unknown_source_is_rejected(client, register_and_verify, seeded):
    register_and_verify(client)
    response = client.get("/api/macro-event/detections?source=twitter")
    assert response.status_code == 400
    assert "must be one of" in response.json()["detail"]


def test_pagination_is_stable_across_pages(client, register_and_verify, seeded):
    """All three sources on one tick share a detected_at, so ordering on the
    timestamp alone would leave their relative order unspecified and a paged
    read could repeat or skip a row. The id tiebreak is what prevents it."""
    register_and_verify(client)
    first = client.get("/api/macro-event/detections?limit=4&offset=0").json()
    second = client.get("/api/macro-event/detections?limit=4&offset=4").json()
    third = client.get("/api/macro-event/detections?limit=4&offset=8").json()

    ids = [d["id"] for d in first["detections"] + second["detections"] + third["detections"]]
    assert len(ids) == 9
    assert len(set(ids)) == 9  # no repeats, no skips
    assert first["limit"] == 4 and second["offset"] == 4


def test_full_snapshot_is_exposed_verbatim(client, register_and_verify, seeded):
    register_and_verify(client)
    body = client.get("/api/macro-event/detections?limit=1").json()
    assert json.loads(body["detections"][0]["raw_metrics_json"])["source"] == "edgar"


def test_nothing_is_escalated_in_this_phase(client, register_and_verify, seeded):
    register_and_verify(client)
    body = client.get("/api/macro-event/detections").json()
    assert all(d["escalated"] is False for d in body["detections"])
