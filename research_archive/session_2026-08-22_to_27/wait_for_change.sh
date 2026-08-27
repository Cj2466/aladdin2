#!/bin/bash
# Polls gen_dashboard.py every INTERVAL seconds (default 12) for up to MAX_ITERS
# iterations (default 45, i.e. ~9 minutes), and returns as soon as the computed
# state differs from the last PUBLISHED state (tracked in poll_state/last_key.txt),
# or as soon as the workflow's output file goes non-empty, or the 3-hour wall-clock
# cap (tracked in poll_state/start_time.txt) is hit.
set -uo pipefail
DIR="/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad"
STATE_DIR="$DIR/poll_state"
mkdir -p "$STATE_DIR"
LAST_KEY_FILE="$STATE_DIR/last_key.txt"
START_TIME_FILE="$STATE_DIR/start_time.txt"

if [ ! -f "$START_TIME_FILE" ]; then
  date +%s > "$START_TIME_FILE"
fi
START_TIME="$(cat "$START_TIME_FILE")"
CAP_SECONDS=10800  # 3 hours

LAST_KEY="$(cat "$LAST_KEY_FILE" 2>/dev/null || echo "")"
MAX_ITERS=${1:-45}
INTERVAL=${2:-12}

i=0
while [ "$i" -lt "$MAX_ITERS" ]; do
  NOW="$(date +%s)"
  ELAPSED=$((NOW - START_TIME))
  if [ "$ELAPSED" -ge "$CAP_SECONDS" ]; then
    echo "CAP_REACHED"
    echo "ELAPSED=$ELAPSED"
    exit 0
  fi

  OUT="$(python3 "$DIR/gen_dashboard.py")"
  KEY_LINE="$(echo "$OUT" | grep '^STATE_KEY=')"
  KEY="${KEY_LINE#STATE_KEY=}"
  DONE_LINE="$(echo "$OUT" | grep '^DONE=')"
  SUMMARY="$(echo "$OUT" | grep '^SUMMARY')"

  if [ "$DONE_LINE" = "DONE=True" ]; then
    echo "WORKFLOW_DONE"
    echo "KEY=$KEY"
    echo "$SUMMARY"
    exit 0
  fi

  if [ "$KEY" != "$LAST_KEY" ]; then
    echo "CHANGED"
    echo "KEY=$KEY"
    echo "$SUMMARY"
    exit 0
  fi

  i=$((i+1))
  sleep "$INTERVAL"
done

echo "NOCHANGE_TIMEOUT"
echo "KEY=$KEY"
echo "$SUMMARY"
echo "ELAPSED=$((($(date +%s)) - START_TIME))"
