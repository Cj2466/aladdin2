# SEC Financial Statement Data Sets — verified structure (orchestrator probe, 2026-09-12)
2024q1.zip = 124,336,804 bytes (HTTP 200, SEC user agent). Members: sub.txt 1.8MB / pre.txt 90MB /
num.txt 487MB / tag.txt 19MB / readme.htm.
sub.txt columns include: adsh, cik, name, sic, form, period, fy, fp, **filed** (SEC receipt date,
YYYYMMDD) — a genuine point-in-time key, 6,029 filings and ~5.9k CIKs in this one quarter.
num.txt columns: adsh, tag, version, ddate, qtrs, uom, segments, coreg, value, footnote — 3,428,695
rows for the quarter.
Implication for Step A3: a whole-market POINT-IN-TIME accounting panel is free and compact if
num.txt is streamed and filtered to the tags a predictor needs (the nport_provider's range-request
+ filter + per-quarter gzip pattern applies unchanged). ~44 quarters 2016q1→2026q2.
