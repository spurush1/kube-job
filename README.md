# Kubernetes Job Scaling Prototype - Run Instructions

This guide explains how to run the project locally using Minikube.

## Prerequisites
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) installed
- [Docker](https://docs.docker.com/get-docker/) installed
- [Python 3](https://www.python.org/) installed
- [Kubectl](https://kubernetes.io/docs/tasks/tools/) installed


## ⚙️ Scaling Behavior
1. **Burst Scaling**: If the queue depth is high (>40), the system spawns **multiple workers (up to 5)** at once to ramp up quickly.
2. **Safe Scale Down**: The system monitors **Unacknowledged Messages**. It will NEVER delete a worker that is busy processing. It only scales down when the system is completely idle (Queue=0, Unacked=0) for 30 seconds.

## 🧪 Testing the System

### 1. Generate Test Data
```bash
python data/generate_data.py
# Creates 'data.csv'
```

### 2. Trigger Jobs
```bash
curl -X POST -F "file=@data.csv" http://localhost:8000/upload
```

### 3. Observe
- Watch the **Dashboard** at `localhost:8080`.
- Use the CLI dashboard helper:
  ```bash
  ./dashboard.sh -w
  ```

## 🛠️ Manual Operations (Without Script)
If you prefer running commands manually:

```bash
# Build
docker build -t producer:latest ./producer
docker build -t worker:latest ./worker
docker build -t scaler:latest ./scaler

# Deploy
kubectl apply -f infra/k8s/rabbitmq.yaml
kubectl apply -f infra/k8s/producer.yaml
kubectl apply -f infra/k8s/scaler.yaml

# Port Forward
kubectl port-forward service/producer 8000:8000 &
kubectl port-forward service/scaler 8080:8000 &
```

## FAQ

### 1. What happens if I scale to 10,000 jobs?
Kubernetes puts extra Pods in **`Pending`** state until resources are available. The system processes at maximum capacity without crashing.

### 2. What if a worker crashes?
RabbitMQ guarantees **at-least-once delivery**. If a worker crashes before Ack, the message is requeued and processed by another worker.

## 🏗️ How to Add a New Job Type (Extensibility)
The platform is designed to be **Producer-Agnostic** and **Worker-Specific**.

### Architecture
- **producer**: A single, generic Gateway. It accepts a file, reads `jobs.config.json` to find the correct queue, and pushes the data. **No new code needed here** (unless you need to support non-CSV formats).
- **scaler**: A generic Orchestrator. It reads `jobs.config.json` and manages queues. **No new code needed here**.
- **workers**: **Specific** logic. You create a new Docker image for each new job type (e.g., `worker-pdf`, `worker-image-resize`).

### Steps to add "New Job"
1. **Create Worker**: Write your python script (simulated logic) and Dockerfile. Build it: `docker build -t worker-new ...`
2. **Update Config**: Add to `jobs.config.json`:
   ```json
   "new-job": { "queue": "queue_new", "image": "worker-new:latest", "threshold": 10 }
   ```
3. **Deploy Config**:
   ```bash
   kubectl create configmap jobs-config ... # (See manage.sh)
   kubectl rollout restart deployment/scaler
   kubectl rollout restart deployment/producer
   ```
4. **Submit**:
   ```bash
   curl ... http://localhost:8000/submit/new-job
   ```
