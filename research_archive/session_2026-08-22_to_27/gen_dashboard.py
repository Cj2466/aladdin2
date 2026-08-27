#!/usr/bin/env python3
"""Generates the pipeline-tracking dashboard HTML from journal.jsonl + output file state.
Run repeatedly; writes to OUT_HTML. Prints a one-line state summary + a STATE_KEY line
whose value changes iff the rendered state changed (used by the poll loop to decide
whether a republish is needed).
"""
import json, os, sys, html, datetime

JOURNAL = "/Users/choonhakunjaroonwatthana/.claude/projects/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/subagents/workflows/wf_9fd00b72-30a/journal.jsonl"
OUTPUT_FILE = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/tasks/we5eep03a.output"
OUT_HTML = "/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/pipeline_dashboard.html"

PHASE_DEFS_FULL = [
    ("infra", "Infra", 3),
    ("infraverify", "Infra Verify", 2),
    ("assetbuild", "Asset Build", 2),
    ("assetverify", "Asset Verify", 2),
    ("report", "Report", 1),
]
PHASE_DEFS_SKIP = [
    ("infra", "Infra", 3),
    ("infraverify", "Infra Verify", 2),
    ("assetbuild", "Asset Build", 0),
    ("assetverify", "Asset Verify", 0),
    ("report", "Report", 1),
]

ROLE_KEYWORDS = {
    "infra": {
        "alpaca-verify": ["alpaca", "delisted", "delisting"],
        "harness-prep": ["membership_fn", "financing_bps", "landmine", "shared-code", "fixed_universe_membership", "financing-cost"],
        "d1-bug-fix": ["market cap", "market_cap", "get_market_cap_basis", "d1 bug", "d1-bug"],
    },
    "infraverify": {
        "verify harness-prep": ["harness-prep", "financing_bps", "membership_fn", "landmine", "fixed_universe_membership"],
        "verify d1-bug-fix": ["d1-bug-fix", "market cap", "market_cap", "get_market_cap_basis"],
    },
    "assetbuild": {
        "bonds build": ["bond etf", "bonds pattern", " bond ", "treasury", "tlt", "agg", "bnd "],
        "fx build": [" fx ", "foreign exchange", "currency pair", "fx pattern", "eur/usd", "usd/jpy"],
    },
    "assetverify": {
        "verify bonds": ["bond etf", "bonds pattern", " bond ", "treasury"],
        "verify fx": [" fx ", "foreign exchange", "currency pair", "fx pattern"],
    },
    "report": {
        "final report": [],
    },
}

ROLE_BLURB = {
    "alpaca-verify": "independently re-checking the Alpaca delisted-ticker data-vendor claim",
    "harness-prep": "fixing a shared-code landmine + adding a financing-cost config field",
    "d1-bug-fix": "investigating + fixing a market-cap calculation bug",
    "verify harness-prep": "independently verifying the harness-prep build report",
    "verify d1-bug-fix": "independently verifying the d1-bug-fix build report",
    "bonds build": "building the Bonds cross-sectional pattern family (18 patterns)",
    "fx build": "building the FX cross-sectional pattern family",
    "verify bonds": "independently verifying the Bonds build report",
    "verify fx": "independently verifying the FX build report",
    "final report": "consolidating everything into the final summary",
}


def read_journal():
    events = []
    if os.path.exists(JOURNAL):
        with open(JOURNAL, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def build_state():
    events = read_journal()
    started_order = []
    agents = {}  # agentId -> {"result": str|None, "start_idx": int}
    for ev in events:
        aid = ev.get("agentId")
        if aid is None:
            continue
        if ev.get("type") == "started" and aid not in agents:
            agents[aid] = {"result": None, "start_idx": len(started_order)}
            started_order.append(aid)
        elif ev.get("type") == "result":
            if aid not in agents:
                agents[aid] = {"result": None, "start_idx": len(started_order)}
                started_order.append(aid)
            agents[aid]["result"] = ev.get("result", "")

    total_started = len(started_order)
    total_result = sum(1 for a in agents.values() if a["result"] is not None)

    out_nonempty = os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0

    # ---- path detection ----
    # Full path: >=7 starts is unambiguous proof (assetbuild's 2 agents launch in parallel
    # right after infraverify's 5 agents fully resolve; only the full path ever reaches 7).
    # Skip path: exactly 6 total agents ever (3 infra + 2 infraverify + 1 report).
    if total_started >= 7:
        path = "full"
        confirmed = True
    elif total_started == 6 and (agents[started_order[5]]["result"] is not None or out_nonempty):
        path = "skip"
        confirmed = True
    else:
        path = "full"  # assumption per instructions, until proven otherwise
        confirmed = False

    defs = PHASE_DEFS_FULL if path == "full" else PHASE_DEFS_SKIP
    total_assumed = sum(n for _, _, n in defs)

    # slice agent ids into phases in start order
    phases = []
    cursor = 0
    for key, label, n in defs:
        if n == 0:
            phases.append({"key": key, "label": label, "n": 0, "agent_ids": []})
            continue
        slice_ids = started_order[cursor:cursor + n]
        cursor += n
        phases.append({"key": key, "label": label, "n": n, "agent_ids": slice_ids})

    # role assignment per phase (greedy keyword match + elimination fallback)
    for ph in phases:
        role_map = ROLE_KEYWORDS.get(ph["key"], {})
        candidates = list(role_map.keys())
        assigned = {}  # agent_id -> role
        scores = {}
        for aid in ph["agent_ids"]:
            res = (agents[aid]["result"] or "").lower()
            best_role, best_score = None, 0
            for role, kws in role_map.items():
                score = sum(res.count(kw) for kw in kws)
                if score > best_score:
                    best_role, best_score = role, score
            if best_role and best_score > 0:
                scores[aid] = (best_role, best_score)
        # resolve conflicts: highest score wins a role
        taken = set()
        for aid, (role, score) in sorted(scores.items(), key=lambda kv: -kv[1][1]):
            if role not in taken:
                assigned[aid] = role
                taken.add(role)
        remaining_ids = [a for a in ph["agent_ids"] if a not in assigned]
        remaining_roles = [r for r in candidates if r not in taken]
        if len(remaining_ids) == len(remaining_roles) and remaining_roles:
            for aid, role in zip(remaining_ids, remaining_roles):
                assigned[aid] = role
        ph["roles"] = assigned

    # compute phase status
    active_phase_idx = None
    for i, ph in enumerate(phases):
        if ph["n"] == 0:
            ph["status"] = "skipped"
            continue
        done_ct = sum(1 for aid in ph["agent_ids"] if agents[aid]["result"] is not None)
        ph["done_ct"] = done_ct
        if done_ct == ph["n"] and len(ph["agent_ids"]) == ph["n"]:
            ph["status"] = "done"
        elif len(ph["agent_ids"]) > 0:
            ph["status"] = "running"
            if active_phase_idx is None:
                active_phase_idx = i
        else:
            ph["status"] = "pending"
        ph.setdefault("done_ct", sum(1 for aid in ph["agent_ids"] if agents[aid]["result"] is not None))

    workflow_done = out_nonempty
    if workflow_done:
        for ph in phases:
            if ph["status"] != "skipped":
                ph["status"] = "done"
                ph["done_ct"] = ph["n"]
        active_phase_idx = None

    overall_done = sum(ph.get("done_ct", 0) for ph in phases)
    overall_pct = round(100 * overall_done / total_assumed) if total_assumed else 0
    if workflow_done:
        overall_pct = 100

    state = {
        "path": path,
        "path_confirmed": confirmed,
        "total_started": total_started,
        "total_result": total_result,
        "total_assumed": total_assumed,
        "overall_done": overall_done,
        "overall_pct": overall_pct,
        "workflow_done": workflow_done,
        "phases": phases,
        "agents": agents,
        "active_phase_idx": active_phase_idx,
    }
    return state


def status_pill_class(status):
    return {"pending": "st-pending", "running": "st-running", "done": "st-done", "skipped": "st-skipped"}[status]


def status_word(status):
    return {"pending": "Pending", "running": "Running", "done": "Done", "skipped": "Skipped"}[status]


def esc(s):
    return html.escape(s, quote=True)


def excerpt(text, limit=900):
    text = text.strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rsplit(" ", 1)[0] + "…", True


def render_agent_row(idx, aid, role, agents):
    a = agents[aid]
    role_label = role or f"agent {idx}"
    blurb = ROLE_BLURB.get(role, "")
    if a["result"] is not None:
        status = "done"
        body, truncated = excerpt(a["result"])
        body_html = esc(body).replace("\n", "<br>")
        detail = f'<details class="agent-detail"><summary>Read full result{" (truncated)" if truncated else ""}</summary><div class="agent-body">{body_html}</div></details>'
    else:
        status = "running"
        detail = '<p class="agent-inflight"><span class="dot-pulse" aria-hidden="true"></span>In progress&hellip;</p>'
    pill = f'<span class="pill {status_pill_class(status)}">{status_word(status)}</span>'
    return f'''<li class="agent-row">
  <div class="agent-row-head">
    <span class="agent-name">{esc(role_label)}</span>
    {pill}
  </div>
  {f'<p class="agent-blurb">{esc(blurb)}</p>' if blurb else ""}
  {detail}
</li>'''


def render_phase_agents(ph, agents):
    if ph["status"] == "skipped":
        return '<p class="phase-empty">Skipped — the conditional branch did not run.</p>'
    if not ph["agent_ids"]:
        expected = ph["n"]
        chips = "".join(f'<span class="queued-chip">Queued</span>' for _ in range(expected))
        return f'<div class="queued-row">{chips}</div>'
    rows = []
    for i, aid in enumerate(ph["agent_ids"], start=1):
        role = ph["roles"].get(aid)
        rows.append(render_agent_row(i, aid, role, agents))
    return f'<ul class="agent-list">{"".join(rows)}</ul>'


def render_station(i, ph):
    status = ph["status"]
    n = ph["n"]
    done_ct = ph.get("done_ct", 0)
    sub = "Skipped" if status == "skipped" else f'{done_ct}/{n} done' if n else "—"
    return f'''<div class="station station-{status}" data-phase="{ph['key']}">
  <div class="station-node">
    <span class="station-num">{i}</span>
  </div>
  <div class="station-meta">
    <span class="station-label">{esc(ph['label'])}</span>
    <span class="station-sub">{esc(sub)}</span>
    <span class="pill {status_pill_class(status)}">{status_word(status)}</span>
  </div>
</div>'''


def render_connector(prev_status):
    filled = "filled" if prev_status == "done" else ("half" if prev_status in ("running",) else "")
    return f'<div class="connector {filled}"></div>'


def build_html(state):
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_human = now.strftime("%H:%M:%S UTC")

    phases = state["phases"]
    stations_html = []
    for i, ph in enumerate(phases):
        stations_html.append(render_station(i + 1, ph))
        if i < len(phases) - 1:
            stations_html.append(render_connector(ph["status"]))
    rail_html = "".join(stations_html)

    active_idx = state["active_phase_idx"]
    if state["workflow_done"]:
        banner_state = "done"
        banner_text = "Workflow complete"
        banner_sub = "All phases finished. See the Report phase below for the final summary."
    elif active_idx is not None:
        ph = phases[active_idx]
        banner_state = "running"
        banner_text = f"Currently running: {ph['label']}"
        running_roles = [ph["roles"].get(aid, "agent") for aid in ph["agent_ids"] if state["agents"][aid]["result"] is None]
        if running_roles:
            banner_sub = "In flight: " + ", ".join(esc(r) for r in running_roles)
        else:
            banner_sub = f"{ph.get('done_ct',0)}/{ph['n']} agents done in this phase"
    else:
        banner_state = "pending"
        banner_text = "Waiting to start"
        banner_sub = "No agents have started yet."

    path_note = ""
    if not state["path_confirmed"]:
        path_note = "Assuming the full 10-agent path (Asset Build + Asset Verify run) until evidence shows the conditional branch was skipped."
    elif state["path"] == "skip":
        path_note = "Confirmed: Infra Verify found a real problem, so Asset Build and Asset Verify were skipped entirely. Total path is 8 agents, not 10."
    else:
        path_note = "Confirmed: the full 10-agent path is running (Asset Build + Asset Verify did not get skipped)."

    detail_sections = []
    for i, ph in enumerate(phases, start=1):
        detail_sections.append(f'''<section class="phase-detail" id="phase-{ph['key']}">
  <div class="phase-detail-head">
    <h3><span class="phase-num">{i}</span>{esc(ph['label'])}</h3>
    <span class="pill {status_pill_class(ph['status'])}">{status_word(ph['status'])}</span>
  </div>
  {render_phase_agents(ph, state["agents"])}
</section>''')
    detail_html = "\n".join(detail_sections)

    pct = state["overall_pct"]

    html_out = f'''<!doctype html>
<title>Bonds &amp; FX Pipeline</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper: #eef2f4;
    --paper-raised: #ffffff;
    --paper-sunken: #e2e8ec;
    --ink: #101826;
    --ink-soft: #4a5568;
    --ink-faint: #7c8698;
    --border: #d5dde3;
    --signal: #0f8b96;
    --signal-soft: #dff2f3;
    --status-pending-fg: #64708a;
    --status-pending-bg: #e6e9ef;
    --status-running-fg: #93600a;
    --status-running-bg: #fbead0;
    --status-running-dot: #e2a233;
    --status-done-fg: #176b45;
    --status-done-bg: #dcf1e6;
    --status-done-dot: #2f9e63;
    --status-skipped-fg: #5a4e9c;
    --status-skipped-bg: #ece9fa;
    --status-skipped-dot: #8f7fe0;
    --shadow: 0 1px 2px rgba(16, 24, 38, 0.06), 0 8px 24px -12px rgba(16, 24, 38, 0.18);
    color-scheme: light;
  }}

  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --paper: #0b1220;
      --paper-raised: #121b2e;
      --paper-sunken: #0e1526;
      --ink: #e8ecf3;
      --ink-soft: #aab4c8;
      --ink-faint: #7c869d;
      --border: #24304a;
      --signal: #4fd7e0;
      --signal-soft: #10333a;
      --status-pending-fg: #9aa5bf;
      --status-pending-bg: #1a2338;
      --status-running-fg: #ffcf82;
      --status-running-bg: #3a2a0e;
      --status-running-dot: #ffb84d;
      --status-done-fg: #7de3ac;
      --status-done-bg: #103826;
      --status-done-dot: #4ade93;
      --status-skipped-fg: #c3b6ff;
      --status-skipped-bg: #251f47;
      --status-skipped-dot: #a493f0;
      --shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 8px 24px -12px rgba(0, 0, 0, 0.6);
      color-scheme: dark;
    }}
  }}

  :root[data-theme="dark"] {{
    --paper: #0b1220;
    --paper-raised: #121b2e;
    --paper-sunken: #0e1526;
    --ink: #e8ecf3;
    --ink-soft: #aab4c8;
    --ink-faint: #7c869d;
    --border: #24304a;
    --signal: #4fd7e0;
    --signal-soft: #10333a;
    --status-pending-fg: #9aa5bf;
    --status-pending-bg: #1a2338;
    --status-running-fg: #ffcf82;
    --status-running-bg: #3a2a0e;
    --status-running-dot: #ffb84d;
    --status-done-fg: #7de3ac;
    --status-done-bg: #103826;
    --status-done-dot: #4ade93;
    --status-skipped-fg: #c3b6ff;
    --status-skipped-bg: #251f47;
    --status-skipped-dot: #a493f0;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.4), 0 8px 24px -12px rgba(0, 0, 0, 0.6);
    color-scheme: dark;
  }}

  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    background: var(--paper);
    color: var(--ink);
    font-family: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.55;
    padding: 2.5rem 1.25rem 4rem;
    min-height: 100vh;
  }}
  .wrap {{ max-width: 920px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.75rem; }}

  h1, h2, h3 {{ font-family: "IBM Plex Sans Condensed", ui-sans-serif, system-ui, sans-serif; text-wrap: balance; margin: 0; }}
  code, .mono {{ font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace; font-variant-numeric: tabular-nums; }}

  header.page-head {{ display: flex; flex-direction: column; gap: 0.35rem; }}
  .eyebrow {{
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.72rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--signal);
    display: flex; align-items: center; gap: 0.5rem;
  }}
  .eyebrow .sep {{ color: var(--ink-faint); }}
  h1 {{ font-size: 1.9rem; font-weight: 700; color: var(--ink); }}
  .subhead {{ color: var(--ink-soft); font-size: 0.95rem; max-width: 62ch; }}

  /* ---- summary strip ---- */
  .summary {{
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1.5rem;
    align-items: center;
    background: var(--paper-raised);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    box-shadow: var(--shadow);
  }}
  .banner-state {{ display: flex; align-items: center; gap: 0.65rem; font-family: "IBM Plex Sans Condensed"; font-weight: 600; font-size: 1.15rem; }}
  .banner-sub {{ color: var(--ink-soft); font-size: 0.88rem; margin-top: 0.2rem; }}
  .status-dot {{ width: 10px; height: 10px; border-radius: 50%; flex: none; }}
  .status-dot.running {{ background: var(--status-running-dot); animation: pulse 1.6s ease-in-out infinite; }}
  .status-dot.done {{ background: var(--status-done-dot); }}
  .status-dot.pending {{ background: var(--ink-faint); }}

  .meter-block {{ display: flex; flex-direction: column; align-items: flex-end; gap: 0.35rem; min-width: 150px; }}
  .meter-pct {{ font-family: "IBM Plex Mono"; font-weight: 600; font-size: 1.7rem; line-height: 1; }}
  .meter-frac {{ font-family: "IBM Plex Mono"; font-size: 0.78rem; color: var(--ink-faint); }}
  .meter-track {{ width: 150px; height: 8px; border-radius: 5px; background: var(--paper-sunken); overflow: hidden; }}
  .meter-fill {{ height: 100%; background: linear-gradient(90deg, var(--signal), var(--status-done-dot)); border-radius: 5px; transition: width 0.6s ease; }}

  .path-note {{
    font-size: 0.82rem; color: var(--ink-soft);
    background: var(--paper-sunken); border: 1px solid var(--border);
    border-radius: 10px; padding: 0.6rem 0.9rem;
  }}

  /* ---- pipeline rail ---- */
  .rail-card {{
    background: var(--paper-raised); border: 1px solid var(--border); border-radius: 14px;
    padding: 1.5rem 1.25rem; box-shadow: var(--shadow); overflow-x: auto;
  }}
  .rail {{ display: flex; align-items: flex-start; gap: 0; min-width: 640px; }}
  .station {{ display: flex; flex-direction: column; align-items: center; gap: 0.6rem; flex: 1; min-width: 0; }}
  .station-node {{
    width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    border: 2px solid var(--border); background: var(--paper-sunken); color: var(--ink-faint);
    font-family: "IBM Plex Mono"; font-weight: 600; font-size: 0.95rem; flex: none;
  }}
  .station-pending .station-node {{ border-color: var(--border); color: var(--ink-faint); }}
  .station-running .station-node {{
    border-color: var(--status-running-dot); color: var(--status-running-fg); background: var(--status-running-bg);
    animation: pulse-ring 1.8s ease-in-out infinite;
  }}
  .station-done .station-node {{ border-color: var(--status-done-dot); background: var(--status-done-dot); color: #08321e; }}
  .station-skipped .station-node {{ border-color: var(--status-skipped-dot); background: var(--status-skipped-bg); color: var(--status-skipped-fg); }}
  .station-meta {{ display: flex; flex-direction: column; align-items: center; gap: 0.3rem; text-align: center; }}
  .station-label {{ font-family: "IBM Plex Sans Condensed"; font-weight: 600; font-size: 0.92rem; }}
  .station-sub {{ font-family: "IBM Plex Mono"; font-size: 0.74rem; color: var(--ink-faint); }}

  .connector {{ height: 2px; background: var(--border); flex: 0.6; margin-top: 20px; border-radius: 2px; position: relative; top: 0; }}
  .connector.filled {{ background: var(--status-done-dot); }}
  .connector.half {{ background: linear-gradient(90deg, var(--status-running-dot), var(--border)); }}

  /* ---- pills ---- */
  .pill {{
    display: inline-flex; align-items: center; gap: 0.35rem;
    font-family: "IBM Plex Mono"; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase;
    padding: 0.2rem 0.55rem; border-radius: 999px;
  }}
  .st-pending {{ color: var(--status-pending-fg); background: var(--status-pending-bg); }}
  .st-running {{ color: var(--status-running-fg); background: var(--status-running-bg); }}
  .st-running::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--status-running-dot); animation: pulse 1.6s ease-in-out infinite; }}
  .st-done {{ color: var(--status-done-fg); background: var(--status-done-bg); }}
  .st-skipped {{ color: var(--status-skipped-fg); background: var(--status-skipped-bg); }}

  /* ---- phase detail ---- */
  .details-grid {{ display: flex; flex-direction: column; gap: 1rem; }}
  .phase-detail {{
    background: var(--paper-raised); border: 1px solid var(--border); border-radius: 14px;
    padding: 1.1rem 1.35rem; box-shadow: var(--shadow);
  }}
  .phase-detail-head {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 0.75rem; }}
  .phase-detail-head h3 {{ font-size: 1.05rem; display: flex; align-items: baseline; gap: 0.55rem; }}
  .phase-num {{ font-family: "IBM Plex Mono"; color: var(--ink-faint); font-size: 0.85rem; }}

  .agent-list {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.7rem; }}
  .agent-row {{ border-top: 1px solid var(--border); padding-top: 0.7rem; }}
  .agent-row:first-child {{ border-top: none; padding-top: 0; }}
  .agent-row-head {{ display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }}
  .agent-name {{ font-weight: 600; font-size: 0.92rem; text-transform: capitalize; }}
  .agent-blurb {{ color: var(--ink-soft); font-size: 0.84rem; margin: 0.25rem 0 0; }}
  .agent-inflight {{ display: flex; align-items: center; gap: 0.5rem; color: var(--status-running-fg); font-size: 0.84rem; margin: 0.4rem 0 0; }}
  .dot-pulse {{ width: 7px; height: 7px; border-radius: 50%; background: var(--status-running-dot); animation: pulse 1.4s ease-in-out infinite; flex: none; }}

  .agent-detail {{ margin-top: 0.5rem; }}
  .agent-detail summary {{
    cursor: pointer; font-family: "IBM Plex Mono"; font-size: 0.76rem; color: var(--signal);
    list-style: none; display: inline-flex; align-items: center; gap: 0.3rem;
  }}
  .agent-detail summary::-webkit-details-marker {{ display: none; }}
  .agent-detail summary::before {{ content: "▸"; display: inline-block; transition: transform 0.15s ease; }}
  .agent-detail[open] summary::before {{ transform: rotate(90deg); }}
  .agent-detail summary:focus-visible {{ outline: 2px solid var(--signal); outline-offset: 3px; border-radius: 4px; }}
  .agent-body {{
    margin-top: 0.55rem; font-size: 0.82rem; color: var(--ink-soft);
    background: var(--paper-sunken); border: 1px solid var(--border); border-radius: 10px;
    padding: 0.85rem 1rem; max-height: 320px; overflow-y: auto;
  }}

  .queued-row {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
  .queued-chip {{
    font-family: "IBM Plex Mono"; font-size: 0.74rem; color: var(--ink-faint);
    background: var(--paper-sunken); border: 1px dashed var(--border); border-radius: 999px;
    padding: 0.25rem 0.65rem;
  }}
  .phase-empty {{ color: var(--ink-faint); font-size: 0.85rem; font-style: italic; margin: 0; }}

  footer {{
    display: flex; flex-wrap: wrap; gap: 0.4rem 1.1rem; align-items: center;
    color: var(--ink-faint); font-size: 0.78rem; font-family: "IBM Plex Mono";
    border-top: 1px solid var(--border); padding-top: 1rem;
  }}
  footer a {{ color: var(--signal); }}
  #relative-time {{ color: var(--ink-faint); }}

  a {{ color: var(--signal); }}
  a:focus-visible, button:focus-visible {{ outline: 2px solid var(--signal); outline-offset: 2px; }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.35; }}
  }}
  @keyframes pulse-ring {{
    0% {{ box-shadow: 0 0 0 0 color-mix(in srgb, var(--status-running-dot) 45%, transparent); }}
    70% {{ box-shadow: 0 0 0 8px color-mix(in srgb, var(--status-running-dot) 0%, transparent); }}
    100% {{ box-shadow: 0 0 0 0 color-mix(in srgb, var(--status-running-dot) 0%, transparent); }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .status-dot.running, .st-running::before, .dot-pulse {{ animation: none; }}
    .station-running .station-node {{ animation: none; }}
    .meter-fill {{ transition: none; }}
  }}

  @media (max-width: 640px) {{
    .summary {{ grid-template-columns: 1fr; }}
    .meter-block {{ align-items: flex-start; }}
    .meter-track {{ width: 100%; }}
  }}
</style>

<div class="wrap">
  <header class="page-head">
    <div class="eyebrow">multi-asset-phase0-and-bonds-fx <span class="sep">/</span> wf_9fd00b72-30a</div>
    <h1>Bonds &amp; FX Pipeline</h1>
    <p class="subhead">Live status for the background workflow: infra fixes and verification, then the Bonds and FX cross-sectional pattern-family builds and their independent verification, then a final consolidated report.</p>
  </header>

  <section class="summary">
    <div>
      <div class="banner-state">
        <span class="status-dot {banner_state}" aria-hidden="true"></span>
        {esc(banner_text)}
      </div>
      <div class="banner-sub">{banner_sub if banner_sub.startswith("In flight") or banner_sub.startswith("No agents") or banner_sub.startswith("All phases") else esc(banner_sub)}</div>
    </div>
    <div class="meter-block">
      <span class="meter-pct">{pct}%</span>
      <span class="meter-frac">{state['overall_done']}/{state['total_assumed']} agents done</span>
      <div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div></div>
    </div>
  </section>

  <p class="path-note">{esc(path_note)}</p>

  <section class="rail-card" aria-label="Pipeline stages">
    <div class="rail">{rail_html}</div>
  </section>

  <div class="details-grid">
    {detail_html}
  </div>

  <footer>
    <span>Last updated <span id="relative-time" data-updated="{now_iso}">just now</span> ({now_human})</span>
    <span>&middot;</span>
    <span>Task <code>we5eep03a</code></span>
    <span>&middot;</span>
    <span>Run <code>wf_9fd00b72-30a</code></span>
    <span>&middot;</span>
    <span>Polling every ~10&ndash;15s while this page's data source is refreshed</span>
  </footer>
</div>

<script>
(function () {{
  var el = document.getElementById('relative-time');
  if (!el) return;
  var updated = new Date(el.dataset.updated);
  function tick() {{
    var secs = Math.max(0, Math.round((Date.now() - updated.getTime()) / 1000));
    var text;
    if (secs < 5) text = 'just now';
    else if (secs < 60) text = secs + 's ago';
    else text = Math.floor(secs / 60) + 'm ' + (secs % 60) + 's ago';
    el.textContent = text;
  }}
  tick();
  setInterval(tick, 1000);
}})();
</script>
'''
    return html_out


def main():
    state = build_state()
    out = build_html(state)
    with open(OUT_HTML, "w") as f:
        f.write(out)
    # a compact key that changes iff rendered state changes (drives republish decisions)
    key_parts = [
        state["path"], str(state["path_confirmed"]), str(state["total_started"]),
        str(state["total_result"]), str(state["workflow_done"]), str(state["overall_pct"]),
    ]
    for ph in state["phases"]:
        key_parts.append(ph["status"])
        key_parts.append(str(ph.get("done_ct", 0)))
    print("STATE_KEY=" + "|".join(key_parts))
    print("DONE=" + str(state["workflow_done"]))
    print(f"SUMMARY path={state['path']}({'confirmed' if state['path_confirmed'] else 'assumed'}) "
          f"started={state['total_started']} result={state['total_result']} "
          f"pct={state['overall_pct']} done={state['workflow_done']}")


if __name__ == "__main__":
    main()
