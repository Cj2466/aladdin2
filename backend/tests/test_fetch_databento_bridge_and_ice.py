"""End-to-end test of data/research_runs/fetch_databento_bridge_and_ice.py's
main() against a fake Databento client -- no network, no key, no real
`databento` import. The fake client's timeseries.get_range response is
shaped like Databento's own documented OHLCV-1d DataFrame (ts_event index,
symbol/open/high/low/close/volume columns -- per the OHLCVMsg fields cited
in databento_futures.py's module docstring and Databento's public schema
docs), so this proves the request-shaping (dataset/symbols/schema/stype_in/
start/end passed to get_range) and response-parsing (root extraction,
per-root CSV split, manifest write) are both correct without ever touching
the real API. 2026-09-07, phase-2 audit."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

SCRIPT_PATH = _BACKEND / "data" / "research_runs" / "fetch_databento_bridge_and_ice.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("fetch_databento_bridge_and_ice", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Meta:
    def get_cost(self, **kw):
        return 0.05

    def get_billable_size(self, **kw):
        return 50_000

    def list_unit_prices(self, dataset):
        return [{"mode": "historical", "unit_prices": {"ohlcv-1d": 1.0}}]


class _Store:
    def __init__(self, frame):
        self._f = frame

    def to_df(self):
        return self._f


class _TS:
    def __init__(self, glbx_frame, ifus_frame):
        self._frames = {"GLBX.MDP3": glbx_frame, "IFUS.IMPACT": ifus_frame}
        self.calls = []

    def get_range(self, **kw):
        self.calls.append(kw)
        return _Store(self._frames[kw["dataset"]])


class FakeClient:
    """Shaped like databento.Historical: .metadata and .timeseries with the
    documented method names (get_cost, get_billable_size, list_unit_prices,
    timeseries.get_range) -- see databento_futures.py's cited docstrings."""

    def __init__(self, glbx_frame, ifus_frame):
        self.metadata = _Meta()
        self.timeseries = _TS(glbx_frame, ifus_frame)


def _sample_glbx_frame() -> pd.DataFrame:
    # Realistic OHLCV-1d rows for the bridge window: two ES contract months
    # and one CL, on a date after CME_BRIDGE_START (2025-09-13).
    return pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2025-09-15", "2025-09-15", "2025-09-15"]),
            "symbol": ["ESZ5", "ESH6", "CLX5"],
            "open": [6500.0, 6510.0, 63.0],
            "high": [6520.0, 6525.0, 63.5],
            "low": [6480.0, 6495.0, 62.5],
            "close": [6505.25, 6512.5, 63.1],
            "volume": [1_200_000, 45_000, 300_000],
        }
    ).set_index("ts_event")


def _sample_ifus_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2025-09-15", "2025-09-15"]),
            "symbol": ["KCZ5", "SBH6"],
            "open": [380.0, 20.5],
            "high": [385.0, 20.9],
            "low": [378.0, 20.3],
            "close": [383.5, 20.7],
            "volume": [5000, 8000],
        }
    ).set_index("ts_event")


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025, 9, 16, tzinfo=tz)


def test_main_estimates_cost_pulls_both_plans_and_writes_manifest(tmp_path, monkeypatch):
    fake = FakeClient(_sample_glbx_frame(), _sample_ifus_frame())

    module = _load_script()
    monkeypatch.setattr(module, "STORE", tmp_path)
    monkeypatch.setattr(module.db, "make_client", lambda: fake)
    monkeypatch.setattr(module, "datetime", _FixedDatetime)  # so `end` is deterministic

    module.main()

    # request shaping: both plans hit get_range with the documented kwargs
    calls = {c["dataset"]: c for c in fake.timeseries.calls}
    assert calls["GLBX.MDP3"]["schema"] == "ohlcv-1d"
    assert calls["GLBX.MDP3"]["stype_in"] == "parent"
    assert calls["GLBX.MDP3"]["start"] == "2025-09-13"  # bridge window only
    assert calls["IFUS.IMPACT"]["start"] == "2018-12-23"  # full ICE history
    assert "ES.FUT" in calls["GLBX.MDP3"]["symbols"] and "KC.FUT" in calls["IFUS.IMPACT"]["symbols"]

    # response parsing: one CSV per root, correctly split from the parent pull
    es_csv = tmp_path / "GLBX.MDP3" / "ES.csv"
    cl_csv = tmp_path / "GLBX.MDP3" / "CL.csv"
    kc_csv = tmp_path / "IFUS.IMPACT" / "KC.csv"
    assert es_csv.exists() and cl_csv.exists() and kc_csv.exists()
    es_rows = pd.read_csv(es_csv)
    assert len(es_rows) == 2 and set(es_rows["symbol"]) == {"ESZ5", "ESH6"}

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["source"] == "Databento historical ohlcv-1d"
    assert len(manifest["plans"]) == 2
    assert manifest["results"][0]["dataset"] == "GLBX.MDP3"


def test_main_refuses_to_pull_if_cost_estimate_is_unexpectedly_large(tmp_path, monkeypatch):
    fake = FakeClient(_sample_glbx_frame(), _sample_ifus_frame())
    fake.metadata.get_cost = lambda **kw: 999.0  # far outside the scoped estimate

    module = _load_script()
    monkeypatch.setattr(module, "STORE", tmp_path)
    monkeypatch.setattr(module.db, "make_client", lambda: fake)

    with pytest.raises(SystemExit):
        module.main()

    # no data pull was attempted once the guard tripped
    assert fake.timeseries.calls == []
