"""Regenerate scorecards/FAMILY_INVENTORY.json from the real trial-results
table.

Run from backend/ with the venv, against a database that actually has the
research history in it (aladdin2.db on the repo owner's machine, or the
production URL):

    ./venv/bin/python data/research_runs/refresh_family_inventory.py

WHY THIS SCRIPT EXISTS RATHER THAN THE TEST JUST QUERYING THE DB.
cross_sectional_trial_results lives in aladdin2.db, which is gitignored — it
is on the repo owner's machine and in production and nowhere else. A
completeness test that queried it directly would silently pass in every
worktree, in CI, and on a fresh clone, i.e. everywhere an agent actually runs
it. The committed inventory makes the requirement travel with the repo.
tests/test_registration_scorecards.py checks the live DB AGAINST this file
whenever the DB is present, so the snapshot cannot go stale unnoticed.

This script only ever WIDENS the inventory relative to the database it reads:
a family key already in the file is kept even if the database in front of it
does not have that family, because a thinner developer DB must never be able
to shrink a governance requirement.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.services.research_lab.registration_scorecard import (
    FAMILY_INVENTORY_PATH,
    FAMILY_INVENTORY_SCHEMA,
)

QUERY = "select distinct family_key from cross_sectional_trial_results order by family_key"

NOTE = (
    "Every family_key with at least one persisted row in "
    "cross_sectional_trial_results. Each key needs a scorecard under "
    "data/research_runs/scorecards/ (one card may answer for several keys via "
    "covers_family_keys). Regenerate with "
    "data/research_runs/refresh_family_inventory.py; the script only ever adds "
    "keys, never removes them, so a thin developer database cannot shrink the "
    "requirement."
)


def main() -> None:
    with engine.connect() as conn:
        observed = [row[0] for row in conn.execute(text(QUERY))]

    existing: list[str] = []
    if FAMILY_INVENTORY_PATH.exists():
        existing = list(json.loads(FAMILY_INVENTORY_PATH.read_text()).get("family_keys", []))

    merged = sorted(set(existing) | set(observed))
    added = sorted(set(observed) - set(existing))
    kept_only_in_file = sorted(set(existing) - set(observed))

    payload = {
        "schema": FAMILY_INVENTORY_SCHEMA,
        "captured_at": datetime.now(tz=UTC).date().isoformat(),
        "source_query": QUERY,
        "database": settings.database_url.split("://", 1)[0] + "://<redacted>",
        "family_keys": merged,
        "note": NOTE,
    }
    FAMILY_INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAMILY_INVENTORY_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"wrote {FAMILY_INVENTORY_PATH} with {len(merged)} family keys")
    if added:
        print(f"  added from the database: {added}")
    if kept_only_in_file:
        print(f"  kept (in file, absent from this database): {kept_only_in_file}")


if __name__ == "__main__":
    main()
