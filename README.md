# Kubernetes Job Scaling Prototype - Run Instructions

This guide explains how to run the project locally using Minikube.

## Prerequisites
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) installed
- [Docker](https://docs.docker.com/get-docker/) installed
- [Python 3](https://www.python.org/) installed
- [Kubectl](https://kubernetes.io/docs/tasks/tools/) installed

## 🚀 Quick Start (Helper Script)
We provide a helper script `manage.sh` to simplify operations.

1. **Start Minikube**:
    ```bash
    minikube start --driver=docker
    eval $(minikube docker-env)
    ```

2. **Deploy Everything**:
    ```bash
    ./manage.sh up
    ```
    This builds the images and deploys RabbitMQ, Producer, and Scaler.

3. **Access Services**:
    ```bash
    ./manage.sh forward
    # This exposes:
    # - Producer: localhost:8000
    # - Dashboard: localhost:8080
    # - RabbitMQ: localhost:15672
    ```

## 📊 Dashboard
Open **[http://localhost:8080](http://localhost:8080)** to view the enhanced dashboard.

### Features
- **Real-Time Cards**: View Queue Depth, Unacknowledged Messages (active processing), Active Jobs, and Total Consumed.
- **Job Table**: List of all worker jobs with their status and individual processed count.
- **Logs**: Click "View Logs" on any job to debug it instantly.
- **Resource Monitoring**: Tracks Scaler CPU/Memory usage.

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
