"""Unit tests for app/services/market_data/eia_nymex_futures.py. The HTML
fixture reproduces the exact weekly layout EIA served on 2026-09-07 for
RCLC1d.htm (first two weeks of April 1983 and the April-2020 week), with
the values EIA published. No network."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.market_data import eia_nymex_futures as eia

HTML = """
<html><body>
<table><tr><td>Cushing, OK Crude Oil Future Contract 1 (Dollars per Barrel)</td></tr></table>
<table>
<tr><th>Week Of</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th></tr>
<tr><td>1983 Apr- 4 to Apr- 8</td><td>29.44</td><td>29.71</td><td>29.92</td><td>30.17</td><td>30.38</td></tr>
<tr><td>1983 Apr-11 to Apr-15</td><td>30.26</td><td>30.83</td><td>30.82</td><td>30.67</td><td>30.48</td></tr>
<tr><td>2020 Apr-20 to Apr-24</td><td>-37.63</td><td>10.01</td><td>13.78</td><td>16.50</td><td>16.94</td></tr>
<tr><td>2020 Apr-27 to May- 1</td><td>12.78</td><td>12.34</td><td></td><td>18.84</td><td>19.78</td></tr>
</table>
</body></html>
"""


def test_weekly_table_becomes_daily_series_with_correct_weekday_dates():
    s = eia.parse_weekly_html(HTML)
    assert s.loc[pd.Timestamp("1983-04-04")] == pytest.approx(29.44)
    assert s.loc[pd.Timestamp("1983-04-08")] == pytest.approx(30.38)
    assert s.loc[pd.Timestamp("1983-04-15")] == pytest.approx(30.48)
    assert s.index.is_monotonic_increasing


def test_negative_wti_print_is_preserved_not_dropped():
    s = eia.parse_weekly_html(HTML)
    assert s.loc[pd.Timestamp("2020-04-20")] == pytest.approx(-37.63)


def test_blank_cells_are_holes_not_zeros():
    s = eia.parse_weekly_html(HTML)
    assert pd.Timestamp("2020-04-29") not in s.index
    assert s.loc[pd.Timestamp("2020-04-30")] == pytest.approx(18.84)


def test_series_catalogue_covers_four_energy_roots_by_position():
    by_root = {}
    for s in eia.EIA_SERIES:
        by_root.setdefault(s.globex, set()).add(s.position)
    assert by_root == {"CL": {1, 2, 3, 4}, "NG": {1, 2, 3, 4}, "HO": {1, 2, 3, 4}, "RB": {1, 2, 3, 4}}


def test_missing_table_raises():
    with pytest.raises(ValueError):
        eia.parse_weekly_html("<html><body><table><tr><td>x</td></tr></table></body></html>")
