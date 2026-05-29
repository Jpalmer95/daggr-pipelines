#!/bin/bash
# Weekly Space liveness check wrapper
# Runs check_spaces.py and reports status changes

cd /home/jonathan/dev/daggr-pipelines
source .venv/bin/activate

# Run with JSON output for parsing
REPORT=$(python scripts/check_spaces.py --json 2>&1)
EXIT_CODE=$?

# Count status
TOTAL=$(echo "$REPORT" | python -c "import json,sys; data=json.load(sys.stdin); print(len(data))")
RUNNING=$(echo "$REPORT" | python -c "import json,sys; data=json.load(sys.stdin); print(sum(1 for s in data if s['ok']))")
DOWN=$(( TOTAL - RUNNING ))

echo "=== Weekly Space Liveness Report ==="
echo "Total: $TOTAL | Running: $RUNNING | Down: $DOWN"
echo ""

if [ $DOWN -gt 0 ]; then
    echo "⚠️  $DOWN Space(s) currently down:"
    echo "$REPORT" | python -c "
import json, sys
data = json.load(sys.stdin)
for s in data:
    if not s['ok']:
        print(f\"  - {s['space']} ({s['stage']}) [{s['category']}]\")
        if s['error']:
            print(f\"    Error: {s['error'][:80]}\")
"
    echo ""
    echo "Run: python scripts/check_spaces.py for full details"
else
    echo "✓ All $TOTAL Spaces are running"
fi

echo ""
echo "Report generated: $(date)"
exit $EXIT_CODE
