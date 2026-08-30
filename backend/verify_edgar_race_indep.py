"""Does the new max_cache_age_days bound create a concurrent cache-write
race between the two quality families, which the runner ticks in PARALLEL
threads (asyncio.gather over asyncio.to_thread in _tick)?

Before this change, companyfacts cache files were written exactly once, ever
(`if cache_path.exists(): read`). With a 1-day bound, BOTH quality families
rewrite all ~165 files on the first tick of every UTC day, concurrently, via
a non-atomic Path.write_text (truncate-then-write).
"""

import json
import os
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.market_data.edgar_xbrl_provider import EdgarXbrlProvider

# Real cached companyfacts documents in data/edgar_companyfacts average ~4 MB
# (666 MB / 165 files, measured), so match that order of magnitude.
PAYLOAD = {"facts": {"us-gaap": {f"Tag{i}": {"units": {"USD": [{"v": i, "filed": "2025-02-01"}] * 60}} for i in range(2000)}}}
BLOB = json.dumps(PAYLOAD)
print(f"payload bytes: {len(BLOB):,}  (real docs average ~4 MB: 666 MB / 165 files)")

with TemporaryDirectory() as td:
    tmp = Path(td)
    p = tmp / "CIK0000000001.json"
    p.write_text(BLOB)
    old = time.time() - 10 * 86400
    os.utime(p, (old, old))

    reader_prov = EdgarXbrlProvider(cache_dir=tmp, max_cache_age_days=1)
    stop = threading.Event()
    errors: list[str] = []
    n_reads = [0]

    USE_ATOMIC = os.environ.get("ATOMIC") == "1"

    def writer():
        # Exactly what get_company_facts does when the cache has expired.
        while not stop.is_set():
            if USE_ATOMIC:
                EdgarXbrlProvider._write_cache_atomically(p, BLOB)
            else:
                p.write_text(BLOB)
            os.utime(p, (old, old))  # keep it "expired" so the reader keeps re-reading

    def reader():
        while not stop.is_set():
            try:
                if p.exists():
                    json.loads(p.read_text())
                n_reads[0] += 1
            except json.JSONDecodeError as exc:
                errors.append(f"JSONDecodeError: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                return

    tw, tr = threading.Thread(target=writer), threading.Thread(target=reader)
    tw.start()
    tr.start()
    time.sleep(4.0)
    stop.set()
    tw.join()
    tr.join()

    print(f"reads completed before first failure: {n_reads[0]}")
    print(f"torn/partial reads observed: {len(errors)}")
    for e in errors[:3]:
        print("   ", e[:160])
    print()
    print("REAL:" if errors else "NOT REPRODUCED in this harness:",
          "concurrent non-atomic rewrite of a shared cache file")

print()
print("Consequence if it fires in production: json.JSONDecodeError is NOT an")
print("EdgarFetchError, so fetch_line_items_for_tickers does not absorb it; it")
print("propagates out of build_*_live_panel, past _process_family's")
print("except (CrossSectionalPanelUnavailableError, MarketDataError), and is")
print("logged by _tick's gather(return_exceptions=True). That family skips the")
print("tick and retries in 30 min (by which time the file is fresh), so it")
print("DELAYS a row, never corrupts one -- but it is a new failure mode this")
print("change introduces, and Path.write_text is trivially made atomic.")
