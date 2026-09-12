import csv
import gzip
import io
import statistics
from pathlib import Path

STORE = Path("/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/data/price_store_alpaca/v1")
OUT = Path("data/research_runs/delisting_outcomes_2026-09-12/dead_names.csv")
WINDOW_END = "2026-09-11"
CUTOFF = "2026-08-12"  # 30 days before window end

rows_out = []
files = sorted(STORE.glob("*.csv.gz"))
print(f"total files: {len(files)}")

for i, fp in enumerate(files):
    ticker = fp.name[: -len(".csv.gz")]
    try:
        with gzip.open(fp, "rt", newline="") as f:
            reader = csv.DictReader(f)
            first_bar = None
            last_bar = None
            last_close = None
            n_bars = 0
            dollar_vols = []
            for row in reader:
                n_bars += 1
                if first_bar is None:
                    first_bar = row["date"]
                last_bar = row["date"]
                last_close = row["close"]
                try:
                    dv = float(row["close"]) * float(row["volume"])
                    dollar_vols.append(dv)
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        print(f"ERROR reading {ticker}: {e}")
        continue

    if n_bars == 0 or last_bar is None:
        continue

    if last_bar <= CUTOFF:
        median_dv = statistics.median(dollar_vols) if dollar_vols else None
        rows_out.append(
            {
                "ticker": ticker,
                "first_bar": first_bar,
                "last_bar": last_bar,
                "last_close": last_close,
                "n_bars": n_bars,
                "median_dollar_volume": f"{median_dv:.2f}" if median_dv is not None else "",
            }
        )
    if (i + 1) % 2000 == 0:
        print(f"processed {i+1}/{len(files)}, dead so far: {len(rows_out)}")

print(f"TOTAL DEAD NAMES: {len(rows_out)}")

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=["ticker", "first_bar", "last_bar", "last_close", "n_bars", "median_dollar_volume"]
    )
    writer.writeheader()
    writer.writerows(rows_out)

print(f"wrote {OUT}")
