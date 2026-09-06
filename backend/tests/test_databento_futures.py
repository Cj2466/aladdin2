"""Unit tests for app/services/market_data/databento_futures.py, against a
fake client that records the calls. No network, no key, no `databento`
import (the real client is imported lazily and only by make_client)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.services.market_data import databento_futures as db


class _Meta:
    def __init__(self):
        self.calls = []

    def get_cost(self, **kw):
        self.calls.append(("get_cost", kw))
        return 0.42

    def get_billable_size(self, **kw):
        self.calls.append(("get_billable_size", kw))
        return 12345

    def list_unit_prices(self, dataset):
        self.calls.append(("list_unit_prices", dataset))
        return [{"mode": "historical", "unit_prices": {"ohlcv-1d": 1.0}}]


class _Store:
    def __init__(self, frame):
        self._f = frame

    def to_df(self):
        return self._f


class _TS:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def get_range(self, **kw):
        self.calls.append(kw)
        return _Store(self.frame)


class FakeClient:
    def __init__(self, frame=None):
        self.metadata = _Meta()
        self.timeseries = _TS(frame if frame is not None else pd.DataFrame())


def test_plans_cover_31_globex_and_3_ice_roots_as_parent_symbols():
    plans = db.build_plans(date(2026, 9, 5))
    assert [p.dataset for p in plans] == ["GLBX.MDP3", "IFUS.IMPACT"]
    assert len(plans[0].symbols) == 31 and "ES.FUT" in plans[0].symbols and "BZ.FUT" in plans[0].symbols
    assert plans[1].symbols == ["KC.FUT", "SB.FUT", "CT.FUT"]
    assert all(p.schema == "ohlcv-1d" and p.stype_in == "parent" for p in plans)
    assert plans[0].start == date(2010, 6, 6) and plans[1].start == date(2018, 12, 23)


def test_estimate_cost_uses_documented_metadata_endpoints_and_spends_nothing():
    client = FakeClient()
    out = db.estimate_cost(client, db.build_plans(date(2026, 9, 5)))
    names = [c[0] for c in client.metadata.calls]
    assert names.count("get_cost") == 2 and names.count("get_billable_size") == 2 and names.count("list_unit_prices") == 2
    kw = client.metadata.calls[0][1]
    assert kw["schema"] == "ohlcv-1d" and kw["stype_in"] == "parent" and kw["start"] == "2010-06-06"
    assert out[0]["cost_usd"] == pytest.approx(0.42) and out[0]["billable_bytes"] == 12345
    assert client.timeseries.calls == []  # no data pulled


def test_offline_size_estimate_is_small_relative_to_credit():
    plans = db.build_plans(date(2026, 9, 5))
    total_mb = sum(db.estimated_bytes(p) for p in plans) / 1e6
    assert 10 < total_mb < 500  # tens of MB, not GB


def test_pull_writes_one_csv_per_root(tmp_path: Path):
    frame = pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-02"]),
            "symbol": ["ESH4", "ESM4", "CLG4"],
            "close": [4800.0, 4830.0, 70.5],
            "volume": [1, 2, 3],
        }
    ).set_index("ts_event")
    client = FakeClient(frame)
    plan = db.build_plans(date(2024, 1, 3))[0]
    out = db.pull_ohlcv_1d(client, plan, tmp_path)
    assert out["per_root"] == {"ES": 2, "CL": 1}
    assert (tmp_path / "GLBX.MDP3" / "ES.csv").exists()
    assert client.timeseries.calls[0]["stype_in"] == "parent"


def test_make_client_refuses_without_key(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        db.make_client()
