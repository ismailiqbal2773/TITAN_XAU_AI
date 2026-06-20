#!/bin/bash
# TITAN XAU AI — Sequential Batch Runner
# Runs N batches in one Bash session, optimized for agent tool timeout (8 min).
# Each batch is 2-3 days to stay within per-batch timeout.

cd /home/z/my-project
PY=/home/z/.venv/bin/python
SCRIPT=/home/z/my-project/scripts/real_data/fast_download.py

# Args: list of "START END" pairs
BATCHES=("$@")
TOTAL=${#BATCHES[@]}
echo "=== Running $TOTAL batches sequentially ==="
echo ""

i=0
for batch in "${BATCHES[@]}"; do
  i=$((i+1))
  start=$(echo "$batch" | awk '{print $1}')
  end=$(echo "$batch" | awk '{print $2}')
  echo "[$i/$TOTAL] $start → $end"
  timeout 200 $PY "$SCRIPT" "$start" "$end" 2>&1 | grep -E "(bars|EMPTY|FAILED|Done)" | head -10
  echo ""
done

echo "=== Final file count ==="
ls /home/z/my-project/titan/data/sources/dukascopy/daily/XAUUSD_M1_*.parquet 2>/dev/null | wc -l
