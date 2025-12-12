#!/bin/bash

# Dashboard script for Kubernetes Job Scaler project
# Provides monitoring and logging capabilities

COMMAND=$1
VALUE=$2

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 {summary|watch|logs <component>|all}"
    echo "  summary     : Show current status of queue, scaler, and jobs (default)"
    echo "  watch       : Continuously watch the summary view"
    echo "  logs <comp> : Stream logs for 'scaler', 'producer', or 'worker' (random pod)"
    echo "  all         : Show all related Kubernetes resources"
    exit 1
}

get_scaler_pod() {
    kubectl get pods -l app=scaler -o jsonpath="{.items[0].metadata.name}" 2>/dev/null
}

get_rabbitmq_pod() {
    kubectl get pods -l app=rabbitmq -o jsonpath="{.items[0].metadata.name}" 2>/dev/null
}

show_header() {
    clear
    echo -e "${BLUE}=================================================${NC}"
    echo -e "${BLUE}   Kubernetes Job Scaler Dashboard   ${NC}"
    echo -e "${BLUE}=================================================${NC}"
    echo "Time: $(date)"
    echo ""
}

show_summary() {
    SCALER_POD=$(get_scaler_pod)
    RABBITMQ_POD=$(get_rabbitmq_pod)
    
    # 1. Scaler Metrics
    echo -e "${YELLOW}[ Scaler Metrics ]${NC}"
    if [ -n "$SCALER_POD" ]; then
        # Fetch stats from the scaler's API (using exec curl inside the pod or just assuming internal access isn't easy, 
        # let's try to query the service if port-forwarded, BUT simply, let's use the container logs or just access the pod directly if possible.
        # Since we don't have a LoadBalancer/NodePort easily for CLI, we can try `kubectl exec` to run a script OR curl localhost if available in the pod.
        # But wait, the scaler image might not have curl.
        # safer bet: rely on what we can see from K8s API + Logs or just what manage.sh does.
        # Actually, let's try to fetch the metrics from the API endpoint if possible using kubectl proxy or port-forward. 
        # For simplicity in this script, we can get valid info from the POD logs which print "Queue depth: X, Active jobs: Y".
        
        # Grabbing last metric log line
        LAST_LOG=$(kubectl logs "$SCALER_POD" --tail=20 | grep "Queue depth:" | tail -n 1)
        if [ -n "$LAST_LOG" ]; then
            echo "  $LAST_LOG"
        else
            echo "  Waiting for metrics..."
        fi
        
        # Also get max jobs env var
        MAX_JOBS=$(kubectl get deployment scaler -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='MAX_JOBS')].value}")
        echo "  Configured Max Jobs: $MAX_JOBS"
        
    else
        echo -e "${RED}  Scaler pod not found!${NC}"
    fi
    echo ""

    # 2. Job Statistics
    echo -e "${YELLOW}[ Worker Jobs ]${NC}"
    TOTAL_JOBS=$(kubectl get jobs -l app=worker-job --no-headers 2>/dev/null | wc -l)
    RUNNING_JOBS=$(kubectl get jobs -l app=worker-job --field-selector status.active=1 --no-headers 2>/dev/null | wc -l)
    SUCCEEDED_JOBS=$(kubectl get jobs -l app=worker-job --field-selector status.successful=1 --no-headers 2>/dev/null | wc -l)
    FAILED_JOBS=$(kubectl get jobs -l app=worker-job --field-selector status.failed=1 --no-headers 2>/dev/null | wc -l)

    echo "  Active (Running): $RUNNING_JOBS"
    echo "  Succeeded:        $SUCCEEDED_JOBS"
    echo "  Failed:           $FAILED_JOBS"
    echo "  Total Created:    $TOTAL_JOBS"
    echo ""

    # 3. Pod Health
    echo -e "${YELLOW}[ Infrastructure Health ]${NC}"
    kubectl get pods -l 'app in (scaler,rabbitmq,producer)' -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount
    echo ""
}

case "$COMMAND" in
    summary|"")
        show_header
        show_summary
        ;;

    watch|w)
        while true; do
            show_header
            show_summary
            echo -e "\n${BLUE}(Press Ctrl+C to exit)${NC}"
            sleep 2
        done
        ;;

    logs|l)
        COMPONENT=$VALUE
        if [ -z "$COMPONENT" ]; then
            echo "Error: Missing component name for logs."
            usage
        fi
        
        echo -e "${BLUE}Streaming logs for $COMPONENT...${NC}"
        
        if [ "$COMPONENT" == "worker" ]; then
             # Pick one random active worker or just the latest job
             # This is tricky as workers come and go. Let's try to follow the logs of the scaler which prints interesting stuff, 
             # OR just pick the latest worker pod.
             POD=$(kubectl get pods -l app=worker-job --sort-by=.metadata.creationTimestamp -o jsonpath="{.items[-1].metadata.name}" 2>/dev/null)
             if [ -z "$POD" ]; then
                 echo "No worker pods found."
                 exit 1
             fi
             echo "Attaching to pod: $POD"
             kubectl logs -f "$POD"
             
        elif [ "$COMPONENT" == "scaler" ] || [ "$COMPONENT" == "rabbitmq" ] || [ "$COMPONENT" == "producer" ]; then
             # Simple deployment pods
             kubectl logs -f -l app="$COMPONENT"
        else
             echo "Unknown component: $COMPONENT. Try: scaler, worker, producer, rabbitmq"
             exit 1
        fi
        ;;

    all|a)
        echo -e "${BLUE}--- Deployments ---${NC}"
        kubectl get deployments
        echo -e "\n${BLUE}--- Pods ---${NC}"
        kubectl get pods
        echo -e "\n${BLUE}--- Jobs ---${NC}"
        kubectl get jobs
        echo -e "\n${BLUE}--- Services ---${NC}"
        kubectl get services
        ;;

    *)
        usage
        ;;
esac
