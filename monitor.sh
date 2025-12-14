#!/bin/bash

# CLI Monitor for Job Platform
# Usage: ./monitor.sh [refresh_interval]

INTERVAL=${1:-2}
SCALER_URL="http://localhost:8080"

# Check if scaler is reachable
if ! curl -s $SCALER_URL/stats > /dev/null; then
    echo "Error: Scaler not reachable at $SCALER_URL"
    echo "Make sure you ran './manage.sh forward'"
    exit 1
fi

while true; do
    clear
    echo "📊 Job Platform Monitor (Ctrl+C to stop)"
    echo "========================================"
    
    # Fetch stats
    DATA=$(curl -s $SCALER_URL/stats)
    
    # Parse Metrics (using python json.tool as generic jq)
    METRICS=$(echo "$DATA" | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin)['metrics']))")
    JOBS=$(echo "$DATA" | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin)['jobs']))")
    
    Q_DEPTH=$(echo "$METRICS" | python3 -c "import sys, json; print(json.load(sys.stdin)['queue_depth'])")
    ACTIVE=$(echo "$METRICS" | python3 -c "import sys, json; print(json.load(sys.stdin)['active_jobs'])")
    CONSUMED=$(echo "$METRICS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_consumed', 0))")
    CPU=$(echo "$METRICS" | python3 -c "import sys, json; print(json.load(sys.stdin)['cpu_percent'])")
    
    echo "Queue Depth : $Q_DEPTH"
    echo "Active Jobs : $ACTIVE"
    echo "Processed   : $CONSUMED"
    echo "System CPU  : $CPU%"
    echo "----------------------------------------"
    echo "Recent Jobs:"
    echo "NAME                          | TYPE             | STATUS    | PROCESSED"
    echo "----------------------------------------------------------------------"
    
    # Python script to format table
    echo "$JOBS" | python3 -c "
import sys, json
jobs = json.load(sys.stdin)
for j in jobs[:10]:
    name = (j['name'] + ' ' * 30)[:28]
    jtype = (j.get('type', 'generic') + ' ' * 16)[:16]
    status = (j['status'] + ' ' * 10)[:10]
    processed = str(j.get('processed', 0))
    print(f'{name} | {jtype} | {status} | {processed}')
"
    
    echo "----------------------------------------"
    echo "Last Updated: $(date)"
    sleep $INTERVAL
done
