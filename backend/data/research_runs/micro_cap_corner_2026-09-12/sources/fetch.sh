#!/bin/bash
# fetch.sh <name> <url>  -> saves <name>.pdf (or .html), prints sha256, extracts text
set -u
name="$1"; url="$2"
ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
tmp="${name}.raw"
curl -sSL -A "$ua" -o "$tmp" "$url"
ft=$(file -b --mime-type "$tmp")
if [ "$ft" = "application/pdf" ]; then mv "$tmp" "${name}.pdf"; f="${name}.pdf"; pdftotext -layout "$f" "${name}.txt";
else mv "$tmp" "${name}.html"; f="${name}.html"; fi
echo "FILE=$f SIZE=$(wc -c < "$f") MIME=$ft"
shasum -a 256 "$f"
