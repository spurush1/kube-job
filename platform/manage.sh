#!/bin/bash

# Utility script for Kubernetes Job Scaler project

COMMAND=$1
VALUE=$2

usage() {
    echo "Usage: $0 {up|down|clean|scale <limit>}"
    echo "  up      : Deploy RabbitMQ, Producer, and Scaler"
    echo "  down    : Delete all project resources"
    echo "  clean   : Delete all running worker jobs"
    echo "  scale N : Set maximum job limit to N and restart scaler"
    echo "  forward : Start port-forwarding for all services (Blocking)"
    echo "  up-frontend : Rebuild and restart Dashboard"
    echo "  up-backend  : Rebuild and restart Scaler & Producer"
    exit 1
}

if [ -z "$COMMAND" ]; then
    usage
fi

build_frontend() {
    echo "🎨 Building Dashboard Image..."
    eval $(minikube docker-env)
    cd platform/dashboard
    npm install && npm run build
    docker build -t dashboard:latest .
    cd ../..
}

build_backend() {
    echo "⚙️ Building Backend Images..."
    eval $(minikube docker-env)
    docker build -t scaler:latest platform/scaler/
    docker build -t producer:latest platform/producer/
}

up_frontend() {
    build_frontend
    # Restart deployment
    kubectl rollout restart deployment/dashboard
    echo "✅ Dashboard updated!"
}

up_backend() {
    build_backend
    kubectl rollout restart deployment/scaler
    kubectl rollout restart deployment/producer
    echo "✅ Backend updated!"
}

case "$COMMAND" in
    up)
        echo "🚀 Starting services..."
        
        # Build images first
        build_backend
        build_frontend

        echo "Applying Infra..."
        kubectl apply -f platform/infra/k8s/rabbitmq.yaml
        kubectl apply -f platform/infra/k8s/postgres.yaml
        
        # Create ConfigMap for Environment Variables (from .secrets.env or defaults)
        SECRET_NAME_VAL=${SECRET_NAME:-"hub-secret"}
        echo "Creating platform-env ConfigMap (SECRET_NAME=$SECRET_NAME_VAL)..."
        kubectl create configmap platform-env \
            --from-literal=SECRET_NAME=$SECRET_NAME_VAL \
            --dry-run=client -o yaml | kubectl apply -f -

        echo "Updating Jobs ConfigMap..."
        kubectl create configmap jobs-config \
            --from-file=platform/jobs.config.json \
            --dry-run=client -o yaml | kubectl apply -f -

        echo "Applying Producer..."
        kubectl apply -f platform/infra/k8s/producer.yaml
        echo "Applying Scaler..."
        kubectl apply -f platform/infra/k8s/scaler.yaml
        echo "Applying Dashboard..."
        kubectl apply -f platform/infra/k8s/dashboard.yaml
        echo "✅ Done! Services are starting."
        ;;
    
    down)
        echo "🛑 Stopping services..."
        kubectl delete -f platform/infra/k8s/scaler.yaml --ignore-not-found
        kubectl delete -f platform/infra/k8s/producer.yaml --ignore-not-found
        kubectl delete -f platform/infra/k8s/rabbitmq.yaml --ignore-not-found
        kubectl delete -f platform/infra/k8s/postgres.yaml --ignore-not-found
        kubectl delete -f platform/infra/k8s/dashboard.yaml --ignore-not-found
        echo "🧹 Cleaning up worker jobs..."
        kubectl delete jobs -l app=worker-job --ignore-not-found
        echo "✅ All resources deleted."
        ;;
        
    clean)
        echo "🧹 Killing all worker jobs..."
        kubectl delete jobs -l app=worker-job
        echo "✅ Worker jobs cleaned."
        ;;
        
    scale)
        if [ -z "$VALUE" ]; then
            echo "Error: Missing limit value."
            usage
        fi
        echo "⚖️  Scaling max jobs to $VALUE..."
        # Update yaml file using sed (compatible with macOS/BSD sed)
        sed -i '' "s/value: \"[0-9]*\"/value: \"$VALUE\"/g" platform/infra/k8s/scaler.yaml
        # For Linux users, it would be: sed -i "s/value: \"[0-9]*\"/value: \"$VALUE\"/g" platform/infra/k8s/scaler.yaml
        
        echo "Applying change..."
        kubectl apply -f platform/infra/k8s/scaler.yaml
        echo "Restarting scaler deployment..."
        kubectl rollout restart deployment/scaler
        echo "✅ Max jobs set to $VALUE."
        ;;

    forward)
        echo "🔌 Port forwarding services..."
        echo "  - Producer API : http://localhost:8000"
        echo "  - Scaler Web   : http://localhost:8080"
        echo "  - RabbitMQ UI  : http://localhost:15672"
        echo ""
        echo "Press Ctrl+C to stop."
        
        # Kill any existing background port-forwards from this script (simple cleanup)
        pkill -f "kubectl port-forward" 2>/dev/null
        
        # Start forwarding in background
        kubectl port-forward service/producer 8000:8000 >/dev/null 2>&1 &
        PF_PID1=$!
        kubectl port-forward service/scaler 8080:8000 >/dev/null 2>&1 &
        PF_PID2=$!
        kubectl port-forward service/dashboard 9090:80 >/dev/null 2>&1 &
        PF_PID4=$!
        kubectl port-forward service/rabbitmq 15672:15672 >/dev/null 2>&1 &
        PF_PID3=$!
        
        # Wait specifically for these PIDs
        wait $PF_PID1 $PF_PID2 $PF_PID3 $PF_PID4
        ;;

    up-frontend)
        up_frontend
        ;;

    up-backend)
        up_backend
        ;;
        
    *)
        usage
        ;;
esac
