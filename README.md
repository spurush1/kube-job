# Kubernetes Job Scaling Prototype - Run Instructions

This guide explains how to run the project locally using Minikube.

## Prerequisites
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) installed
- [Docker](https://docs.docker.com/get-docker/) installed
- [Python 3](https://www.python.org/) installed

## 1. Start Minikube
Start Minikube with the Docker driver:
```bash
minikube start --driver=docker
```

## 2. Point Docker to Minikube
**Crucial Step**: Configure your shell to use Minikube's Docker daemon. This allows Minikube to find the images you build locally.
```bash
eval $(minikube -p minikube docker-env)
```

## 3. Build Docker Images
Build the images for the Producer, Worker, and Scaler components. Run these commands from the project root (`learning/kube-job`):

```bash
docker build -t producer:latest ./producer
docker build -t worker:latest ./worker
docker build -t scaler:latest ./scaler
```

## 4. Deploy to Kubernetes
Apply the Kubernetes manifests to deploy RabbitMQ, the Producer, and the Scaler:

```bash
kubectl apply -f infra/k8s/rabbitmq.yaml
kubectl apply -f infra/k8s/producer.yaml
kubectl apply -f infra/k8s/scaler.yaml
```

Wait a few moments for the pods to start. You can check their status with:
```bash
kubectl get pods
```

## 5. Generate Test Data
Generate a sample CSV file to upload:
```bash
python data/generate_data.py
# This creates a 'data.csv' file in the current directory
```

## 6. Access the Producer
Port-forward the Producer service to access its API from your local machine:
```bash
kubectl port-forward service/producer 8000:8000
```
*Keep this terminal open.*

## 7. Trigger the Job
In a **new terminal window**, upload the generated data to the Producer:

```bash
curl -X POST -F "file=@data.csv" http://localhost:8000/upload
```

## 8. Observe Scaling
Monitor the Scaler logs and the creation of Worker jobs:

```bash
# Watch pods (you should see worker-job-xxxxx pods appearing)
kubectl get pods -w

# Check Scaler logs
kubectl logs -f deployment/scaler
```

The Scaler will check the RabbitMQ queue depth. When it exceeds 20 messages, it will start spawning worker jobs.

## FAQ

### 1. What happens if I scale to 10,000 jobs but run out of memory?
The system is designed to be resilient to resource exhaustion. Kubernetes controls the scheduling:
- If you request more Jobs than your cluster (or Minikube VM) can handle, the extra Pods will go into a **`Pending`** state.
- They will wait in the queue until resources (Memory/CPU) become available (e.g., when other workers finish).
- The system **will not crash**; it will simply saturate the available resources and process at maximum capacity.

### 2. What happens if a worker dies while processing a message?
The system guarantees **at-least-once delivery** using RabbitMQ's acknowledgement mechanism:
- Workers only send an "Wait, I'm done" (Ack) signal to RabbitMQ *after* they have fully processed the message.
- If a pod crashes, is killed, or the node fails *before* sending the Ack, RabbitMQ detects the lost connection.
- RabbitMQ automatically **re-queues the message**.
- Another available worker will pick up that same message and process it. No data is lost.

## Helpful Commands

### Monitoring
```bash
# Watch all pods update in real-time
kubectl get pods -w

# View logs of the scaler
kubectl logs -f deployment/scaler

# View logs of a specific worker (replace pod name)
kubectl logs worker-job-xxxxx

# View queue status via RabbitMQ Management UI
kubectl port-forward service/rabbitmq 15672:15672
# Then open http://localhost:15672 (User: guest, Pass: guest)
```

### Debugging
```bash
# Access shell inside a pod
kubectl exec -it pod-name -- /bin/bash

# Describe a pod to see why it's Pending or failing
kubectl describe pod pod-name

# Delete all worker jobs manually (Cleanup)
kubectl delete jobs -l app=worker-job
```
