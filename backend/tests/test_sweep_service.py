from app.schemas.sweep import SweepGridSpec
from app.services.research_lab.sweep_service import expand_sweep_grid


def test_expand_sweep_grid_product_size_and_filtering():
    grid = SweepGridSpec(fit_window_days=[100, 200], entry_z=[1.5, 2.0], exit_z=[0.0, 1.75], cost_bps=[10.0])
    combos = expand_sweep_grid(grid)

    # 2 x 2 x 2 x 1 = 8 raw combos, minus the ones where exit_z >= entry_z:
    # (entry_z=1.5, exit_z=1.75) is invalid for both fit_window_days values -> 2 dropped.
    assert len(combos) == 6
    for combo in combos:
        assert combo["exit_z"] < combo["entry_z"]


def test_expand_sweep_grid_all_invalid_returns_empty():
    grid = SweepGridSpec(fit_window_days=[100], entry_z=[1.0], exit_z=[1.0, 2.0], cost_bps=[10.0])
    assert expand_sweep_grid(grid) == []


def test_expand_sweep_grid_deterministic_ordering():
    grid = SweepGridSpec(fit_window_days=[100, 200], entry_z=[2.0], exit_z=[0.0], cost_bps=[5.0, 10.0])
    combos1 = expand_sweep_grid(grid)
    combos2 = expand_sweep_grid(grid)
    assert combos1 == combos2


def test_sweep_grid_spec_dedups_and_sorts_values():
    grid = SweepGridSpec(fit_window_days=[200, 100, 200], entry_z=[2.0, 1.5, 2.0])
    assert grid.fit_window_days == [100, 200]
    assert grid.entry_z == [1.5, 2.0]
