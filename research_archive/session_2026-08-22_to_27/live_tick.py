"""Independent end-to-end verification: run ONE real tick of the
cross-sectional forward-validation runner against the real database and the
real yfinance crypto panel, and print exactly what the registration holds
afterwards."""

import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)

from app.db import SessionLocal, engine  # noqa: E402
from app.models.cross_sectional_forward_validation import (  # noqa: E402
    CrossSectionalForwardValidationRegistration,
)
from app.services.research_lab.cross_sectional_forward import (  # noqa: E402
    deserialize_cross_sectional_forward_state,
)
from app.services.research_lab.cross_sectional_forward_validation_runner import (  # noqa: E402
    CrossSectionalForwardValidationRunner,
)

print("DB:", engine.url)


async def main():
    runner = CrossSectionalForwardValidationRunner()
    loaded = runner._load_active_registrations()
    print(f"active cross-sectional registrations loaded: {len(loaded)}")
    for s in loaded:
        print("  ", s.id, s.family_key, s.pattern_id, "last_processed:", s.last_processed_date)
    await runner._tick()

    db = SessionLocal()
    try:
        for r in db.query(CrossSectionalForwardValidationRegistration).all():
            state = deserialize_cross_sectional_forward_state(json.loads(r.carry_state_json))
            print("\n--- after one real tick ---")
            print("id:", r.id, "| status:", r.status)
            print("started_at:", r.started_at, "| last_processed_date:", r.last_processed_date)
            print("last_ticked_at:", r.last_ticked_at)
            print("n_forward_trading_days (realized):", r.n_forward_trading_days)
            print("n_formations:", r.n_formations)
            print("equity:", state.equity, "| rows_since_formation:", state.rows_since_formation)
            print("gross_notional_held:", state.gross_notional_held)
            print("pending_turnover_cost:", state.pending_turnover_cost)
            print("LONG leg:", json.dumps(state.long_weights, indent=None))
            print("SHORT leg:", json.dumps(state.short_weights, indent=None))
            print("formations_json:", r.formations_json)
            print("day_results_json:", r.day_results_json)
    finally:
        db.close()


asyncio.run(main())
