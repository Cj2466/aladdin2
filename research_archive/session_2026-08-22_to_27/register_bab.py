"""Create THE one deliberate, disclosed BAB forward-validation registration
in the real database, owned by the system research account (the same account
that owns every other autonomous research row), starting today."""

from datetime import date

from app.db import SessionLocal, engine
from app.services.research_lab.bab_forward_registration import register_bab_forward_validation
from app.services.research_lab.system_account import get_or_create_system_user

print("DB:", engine.url)
db = SessionLocal()
try:
    system_user = get_or_create_system_user(db)
    print("owner:", system_user.id, system_user.email)
    registration, created = register_bab_forward_validation(db, system_user.id)
    print("created:", created)
    print("id:", registration.id)
    print("family_key:", registration.family_key)
    print("pattern_id:", registration.pattern_id)
    print("module_path:", registration.module_path)
    print("spec_family:", registration.spec_family)
    print("family_n_trials:", registration.family_n_trials)
    print("status:", registration.status)
    print("started_at:", registration.started_at, "  (today is", date.today(), ")")
    print("min_trading_days_threshold:", registration.min_trading_days_threshold)
    print("n_forward_trading_days:", registration.n_forward_trading_days)
    print("n_formations:", registration.n_formations)
    print("last_processed_date:", registration.last_processed_date)
    print("spec_snapshot:", registration.spec_snapshot_json)
    print("config_snapshot:", registration.config_snapshot_json)
    print("carry_state:", registration.carry_state_json)
    print("day_results:", registration.day_results_json)
    print("formations:", registration.formations_json)
    print("config_hash:", registration.config_hash)
    print("spec_fingerprint:", registration.spec_fingerprint)
    print("config_fingerprint:", registration.config_fingerprint)
    print("\nuniverse_rule:\n", registration.universe_rule)
    print("\ncitation:\n", registration.citation)
finally:
    db.close()
