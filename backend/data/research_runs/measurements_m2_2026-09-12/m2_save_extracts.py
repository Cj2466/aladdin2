#!/usr/bin/env python
"""Save, with SHA-256, an extract of every primary EDGAR document quoted in M2_RESULT.md.

Run after m2_odd_lot_offers.py.  Reads m2_output.json, takes the offers named in QUOTED below,
re-fetches each offer's selected document THROUGH THE SAME CACHE, writes
  m2_sources/<slug>.txt   -- the title block plus the odd-lot sentences, verbatim
and prints a markdown table (file, sha256 OF THE RAW DOCUMENT AS FETCHED, url, what it shows)
for m2_SOURCES.md.  The hash is of the raw bytes, not of the extract, so it can be checked
against EDGAR directly.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m2_odd_lot_offers import fetch, odd_lot_sentences, to_text

OUT = Path(__file__).resolve().parent
SRC = OUT / "m2_sources"

# (cik, launch_date) of every offer quoted in M2_RESULT.md, with a one-line note.
QUOTED: list[tuple[str, str, str]] = json.loads((OUT / "m2_quoted.json").read_text())


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]


def main() -> None:
    data = json.loads((OUT / "m2_output.json").read_text())
    rows = {(r["cik"], r["launch_date"]): r for r in data["offers"]}
    lines = ["| extract file | sha256 of the raw document | EDGAR URL | what it shows |",
             "|---|---|---|---|"]
    for cik, launch, note in QUOTED:
        r = rows.get((cik, launch))
        if r is None:
            print(f"MISSING {cik} {launch}", file=sys.stderr)
            continue
        raw = fetch(r["clause_doc_url"])
        sha = hashlib.sha256(raw).hexdigest()
        assert sha == r["doc_sha256"], f"hash drift for {cik} {launch}"
        txt = to_text(raw)
        name = f"{slug(r['issuer'])}_{launch}.txt"
        body = [
            f"SOURCE: {r['clause_doc_url']}",
            f"SHA-256 (raw document as fetched): {sha}",
            f"ISSUER: {r['issuer']}  CIK {cik}  tickers {r['tickers'] or '-'}",
            f"LAUNCH SC TO-I: {launch}   accession {r['launch_accession']}",
            "",
            "--- TITLE BLOCK (first 1,500 characters of the extracted text, verbatim) ---",
            txt[:1500],
            "",
            "--- SENTENCES CONTAINING 'ODD LOT', VERBATIM ---",
        ]
        body += [f"[{i + 1}] {s}" for i, s in enumerate(odd_lot_sentences(txt, 3))]
        (SRC / name).write_text("\n".join(body))
        lines.append(f"| `{name}` | `{sha}` | {r['clause_doc_url']} | {note} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
