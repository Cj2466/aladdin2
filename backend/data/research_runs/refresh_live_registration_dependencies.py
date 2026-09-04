"""Regenerate app/services/research_lab/live_registration_dependencies.json.

    ./venv/bin/python data/research_runs/refresh_live_registration_dependencies.py

WHAT IT DOES. Walks the real import graph, by AST, from each live
registration's own family module and from the shared tick path, and pins a
sha256 of every first-party file that graph reaches. Nothing is hand-listed:
if a family starts importing a new module, the next regeneration picks it up.

WHY THE TRACE ROOT IS THE FAMILY MODULE AND NOT THE REGISTRATION MODULE.
Tracing from *_forward_registration.py gives the same 42-module answer for
all four registrations, because they all reach
cross_sectional_forward_registry, which imports EVERY family. That is a fact
about the registry's import style, not about what any one registration's tick
depends on: a tick resolves ONE family_key and runs ONE family's adapter. So
each entry is traced from the module that adapter actually calls into, plus
the shared tick path every tick runs through regardless.

APPEND-ONLY ACKNOWLEDGEMENTS. Existing acknowledgements are carried over
verbatim. This script will NOT invent one: if a dependency's content has
moved, it re-pins the hash and prints a loud warning naming the entry you
still have to write. Writing it is the human step the whole mechanism exists
to force.
"""

import ast
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
# This script lives under data/research_runs/, so `app` is not importable until
# backend/ is on the path. Kept as a sys.path insert plus function-local imports
# rather than module-level ones after it, so the file needs no E402 suppression
# and stays importable for a `--help`-style read without touching the app.
sys.path.insert(0, str(BACKEND))

# Which family module each registration's adapter actually runs. Read off
# cross_sectional_forward_registry.py's own imports for each FAMILY_KEY block,
# not guessed — see that file's _build_* functions. Kept for every key
# live_registration_family_keys() returns (including retired ones — see
# RETIRED_FAMILY_KEYS below) so this script's own safety check below still
# catches a genuinely new, untracked registration the moment main.py wires one.
TRACE_ROOTS = {
    "quality_cbop": "app.services.research_lab.cross_sectional_quality",
    "quality_noa_industry_neutral": "app.services.research_lab.cross_sectional_quality_neutral",
    "short_interest_ratio": "app.services.research_lab.cross_sectional_short_interest",
    "lazy_prices_jaccard_full": "app.services.research_lab.cross_sectional_lazy_prices",
    "cross_sectional_crypto": "app.services.research_lab.cross_sectional_crypto",
}


# Every tick runs through these regardless of which family it resolves.
SHARED_ROOTS = (
    "app.services.research_lab.cross_sectional_forward",
    "app.services.research_lab.cross_sectional_forward_registry",
    "app.services.research_lab.cross_sectional_forward_validation_runner",
    "app.services.cross_sectional_forward_validation_service",
)

# PINNED BUT NOT TRAVERSED. cross_sectional_forward_registry.py imports EVERY
# family so that resolve_spec() can reach any of them; its transitive closure
# is therefore the whole research library, and tracing through it would put
# every family in the shared set and leave each registration with zero
# distinctive dependencies (measured: 40 shared, 0 each, on the first
# generation of this file). Its own CONTENT is still pinned — a change to an
# adapter absolutely does affect ticks — but the traversal stops there and
# each family is reached from its own root instead.
PIN_WITHOUT_TRAVERSING = {"app.services.research_lab.cross_sectional_forward_registry"}

# WHAT GETS PINNED AT ALL, as a rule rather than case by case: the
# research-arithmetic and market-data surface. Everything else the import
# closure reaches is application plumbing — FastAPI dependency injection,
# ORM models, settings, time helpers — which a live registration's NUMBERS do
# not come from. Pinning those too would make this test fire on unrelated
# application edits, and a drift alarm that cries wolf is one nobody reads.
PINNED_PREFIXES = ("app/services/research_lab/", "app/services/market_data/")

# Non-Python files whose CONTENT is an input to a live registration's numbers.
# A .py-only trace would miss these entirely, and two of the three incidents
# this manifest exists for were about data, not code.
EXTRA_FILES = {
    "app/services/research_lab/global_effective_n.json": (
        "the pooled DSR denominator every family's dsr_n_trials() reads; recomputing it "
        "moves every DSR in the project"
    ),
}

WHY = {
    "app/services/market_data/price_store.py": (
        "the point-in-time raw price store and the CRSP dividend/split adjustment convention "
        "(77e77d7..61bd307, a3ba0bc) — every adjusted price a tick sees comes through here"
    ),
    "app/services/market_data/yfinance_provider.py": (
        "the daily OHLCV path and the frozen-snapshot machinery"
    ),
    "app/services/research_lab/cross_sectional.py": (
        "the replay harness: weights, turnover, the cost model and the financing accrual"
    ),
    "app/services/research_lab/deflated_sharpe.py": "the DSR/PSR formulas themselves",
    "app/services/research_lab/global_effective_n.py": (
        "dsr_n_trials(): max(local grid, pooled effective N)"
    ),
    "app/services/research_lab/metrics.py": "sharpe_ratio, max_drawdown and the annualization",
    "app/services/research_lab/sp500_membership_history.py": (
        "point-in-time universe construction and the was_member gate"
    ),
    "app/services/research_lab/spread_estimator.py": (
        "the edge_spread cost basis — documented as overstating large-cap costs 10-40x, and "
        "swapping the frame changes returns WITHOUT changing any fingerprint"
    ),
    "app/services/research_lab/engine.py": "the walk-forward state machine each replay steps",
}


def module_to_path(mod: str) -> Path | None:
    p = BACKEND / (mod.replace(".", "/") + ".py")
    if p.exists():
        return p
    pkg = BACKEND / mod.replace(".", "/") / "__init__.py"
    return pkg if pkg.exists() else None


def imports_of(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names if a.name.startswith("app."))
        elif (
            isinstance(node, ast.ImportFrom)
            and not node.level
            and node.module
            and node.module.startswith("app")
        ):
            out.add(node.module)
            for a in node.names:
                sub = f"{node.module}.{a.name}"
                if module_to_path(sub) is not None:
                    out.add(sub)
    return out


def trace(roots) -> list[str]:
    """Transitive first-party modules, stopping at PIN_WITHOUT_TRAVERSING and
    keeping only what PINNED_PREFIXES covers."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        if mod in PIN_WITHOUT_TRAVERSING:
            continue
        path = module_to_path(mod)
        if path is None:
            continue
        stack.extend(imports_of(path))
    resolved = [m for m in seen if module_to_path(m) is not None]
    return sorted(m for m in resolved if rel(m).startswith(PINNED_PREFIXES))


def rel(mod: str) -> str:
    return str(module_to_path(mod).relative_to(BACKEND))


def build_dependencies(modules, extra: dict[str, str]) -> list[dict]:
    from app.services.research_lab.live_registration_dependencies import file_sha256

    entries = []
    for mod in modules:
        path = rel(mod)
        entries.append(
            {
                "path": path,
                "sha256": file_sha256(BACKEND / path),
                "why": WHY.get(path, f"reached by the import trace from {mod}"),
            }
        )
    for path, why in sorted(extra.items()):
        entries.append({"path": path, "sha256": file_sha256(BACKEND / path), "why": why})
    return sorted(entries, key=lambda e: e["path"])


def main() -> None:
    from app.services.research_lab.live_registration_dependencies import (
        MANIFEST_PATH,
        SCHEMA,
    )
    from app.services.research_lab.registration_scorecard import (
        RETIRED_LIVE_REGISTRATION_FAMILY_KEYS,
        live_registration_family_keys,
    )

    previous = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    prev_regs = previous.get("registrations", {})
    prev_hashes = {}
    for entry in previous.get("shared_tick_path", []):
        prev_hashes[entry["path"]] = entry["sha256"]
    for entry in prev_regs.values():
        for dep in entry.get("dependencies", []):
            prev_hashes[dep["path"]] = dep["sha256"]

    shared_modules = trace(SHARED_ROOTS)
    # EXTRA_FILES belongs with the shared set: global_effective_n.json is read
    # by global_effective_n.py, which every family's dsr_n_trials() call goes
    # through, so it is shared by construction rather than per-registration.
    shared = build_dependencies(shared_modules, EXTRA_FILES)
    shared_paths = {e["path"] for e in shared}

    registrations = {}
    live = live_registration_family_keys()
    for family_key, pattern_id in sorted(live.items()):
        if family_key in RETIRED_LIVE_REGISTRATION_FAMILY_KEYS:
            continue
        root = TRACE_ROOTS.get(family_key)
        if root is None:
            sys.exit(
                f"no trace root for live registration {family_key!r}. A registration was wired "
                "into app/main.py without being added to TRACE_ROOTS here — add it rather than "
                "letting it go unpinned."
            )
        modules = [m for m in trace([root]) if rel(m) not in shared_paths]
        key = f"{family_key}/{pattern_id}"
        registrations[key] = {
            "family_key": family_key,
            "pattern_id": pattern_id,
            "module_path": rel(root),
            "trace": (
                f"AST import trace from {root}, minus the shared tick path; plus the "
                "non-Python inputs listed in EXTRA_FILES"
            ),
            "dependencies": build_dependencies(modules, {}),
            "acknowledgements": prev_regs.get(key, {}).get("acknowledgements", []),
        }

    payload = {
        "schema": SCHEMA,
        "captured_at": datetime.now(tz=UTC).date().isoformat(),
        "hash_algorithm": "sha256",
        "how_to_regenerate": (
            "./venv/bin/python data/research_runs/refresh_live_registration_dependencies.py"
        ),
        "what_a_mismatch_means": (
            "A dependency of a LIVE forward registration changed content since it was last "
            "pinned. That is not automatically a problem — the price-store rewrite moved "
            "everything and changed no verdict — but it must not pass unnoticed. Re-verify what "
            "the change does to that registration's numbers, append an acknowledgement entry "
            "saying what you re-ran and what you found, and only then re-pin. Bumping a baseline "
            "without a matching acknowledgement is itself a test failure. Never change a "
            "registration's status here; that is the repo owner's decision."
        ),
        "shared_tick_path": shared,
        "registrations": registrations,
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    moved = []
    for entry in shared + [d for r in registrations.values() for d in r["dependencies"]]:
        old = prev_hashes.get(entry["path"])
        if old is not None and old != entry["sha256"]:
            moved.append((entry["path"], old, entry["sha256"]))

    n_pinned = len({e["path"] for e in shared} | {
        d["path"] for r in registrations.values() for d in r["dependencies"]
    })
    print(f"wrote {MANIFEST_PATH}: {len(registrations)} registrations, {n_pinned} distinct files")
    if moved:
        print("\n*** RE-PINNED FILES THAT HAD MOVED — write the acknowledgement entries: ***")
        for path, old, new in moved:
            print(f"  {path}\n    {old}\n -> {new}")
        print(
            "\nEach needs an entry under the affected registration's `acknowledgements` with "
            "what you re-verified and what you found. The test refuses a bumped baseline whose "
            "latest acknowledgement does not name it."
        )


if __name__ == "__main__":
    main()
