"""Production run of Cross-Sectional Round C — launched detached (nohup) so
it survives session/agent-turn boundaries, matching this project's
established resilience pattern for long-running research jobs.

Pre-specified BEFORE seeing any result (per this project's standing
p-hacking discipline): start = MEMBERSHIP_DATA_START, end = today, the full
30-definition ROUND_C_FAMILY as already committed. No parameter here is
chosen after peeking at output.
"""
import sys
import time
from datetime import date

sys.path.insert(0, "/Users/choonhakunjaroonwatthana/Desktop/aladdin2/.claude/worktrees/agent-a327c9fd73bf9f348/backend")

from app.services.research_lab.cross_sectional_patterns import run_round_c_screening
from app.services.research_lab.sp500_membership_history import MEMBERSHIP_DATA_START

REPORT_PATH = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/round_c_final_report.txt"

start_time = time.time()
print(f"Starting Round C screening: {MEMBERSHIP_DATA_START} -> {date.today()}", flush=True)

results, missing = run_round_c_screening(start=MEMBERSHIP_DATA_START, end=date.today())

elapsed = time.time() - start_time

lines = []
lines.append(f"Round C production screening — completed in {elapsed:.1f}s")
lines.append(f"Window: {MEMBERSHIP_DATA_START} -> {date.today()}")
lines.append(f"n_trials (family size, pre-declared): 30")
lines.append(f"Tickers requested but unresolved (no price data at all): {len(missing)}")
lines.append(f"Specs that produced a usable replay (>= MIN_REPLAY_TRADING_DAYS): {len(results)} / 30")
lines.append("")
lines.append(f"{'pattern_id':<32} {'family':<32} {'n_form':>7} {'n_days':>7} {'sharpe':>8} {'dsr':>8} {'psr0':>8}")
for r in results:
    dsr_val = f"{r.deflated_sharpe.dsr:.3f}" if r.deflated_sharpe.dsr is not None else "n/a"
    psr_val = f"{r.deflated_sharpe.psr_vs_zero:.3f}" if r.deflated_sharpe.psr_vs_zero is not None else "n/a"
    lines.append(
        f"{r.pattern_id:<32} {r.family:<32} {r.n_formations:>7} {r.n_trading_days:>7} "
        f"{r.sharpe_annualized:>8.3f} {dsr_val:>8} {psr_val:>8}"
    )

lines.append("")
lines.append("Missing tickers (no price data resolved at all):")
lines.append(", ".join(sorted(missing)) if missing else "(none)")

report = "\n".join(lines)
print(report, flush=True)
with open(REPORT_PATH, "w") as f:
    f.write(report + "\n")

print(f"\nReport written to {REPORT_PATH}", flush=True)
