# Deployment to Production (GKE / EKS / AKS)

Currently, the system runs on **Minikube** (Local). To deploy to a real Kubernetes cluster (Google GKE, AWS EKS, or Azure AKS), follow these steps.

## 1. Prerequisites
- A cloud Kubernetes cluster.
- `kubectl` configured to point to that cluster.
- A Container Registry (Docker Hub, GCR, ECR) to push images.

## 2. Infrastructure Changes

### Storage (Postgres)
Minikube uses `hostPath` for persistence. In production, use a managed **Cloud PVC** or a managed DB service (RDS/CloudSQL).
*   **Action**: Change `postgres-pvc.yaml`.
    ```yaml
    storageClassName: standard-rwo # GKE default
    ```
    Or better, use **Terraform** to provision an RDF/CloudSQL instance and pass credentials via Secrets.

### Ingress (Access)
Minikube uses `NodePort` or `PortForward`. Production uses **Ingress**.
*   **Action**: Create an `ingress.yaml`.
    ```yaml
    apiVersion: networking.k8s.io/v1
    kind: Ingress
    metadata:
      name: platform-ingress
    spec:
      rules:
      - http:
          paths:
          - path: /api
            backend:
              service:
                name: scaler
                port:
                  number: 8000
          - path: /
            backend:
              service:
                name: dashboard
                port:
                  number: 80
    ```

### Secrets (Security)
Do NOT commit `.secrets.env` or use default passwords.
*   **Action**: Use a Secret Manager (e.g., AWS Secrets Manager, Google Secret Manager) or `sealed-secrets`.
*   Manually create secrets in prod:
    ```bash
    kubectl create secret generic hub-secret --from-literal=docker-username=... --from-literal=docker-password=...
    ```

## 3. Build & Push Images
You cannot building images locally and expect the remote cluster to see them (unless using a distinct registry).
1.  **Tag Images**:
    ```bash
    docker tag scaler:latest gcr.io/my-project/scaler:v1
    docker tag producer:latest gcr.io/my-project/producer:v1
    docker tag dashboard:latest gcr.io/my-project/dashboard:v1
    ```
2.  **Push**:
    ```bash
    docker push gcr.io/my-project/scaler:v1
    ...
    ```
3.  **Update YAMLs**:
    Update `scaler.yaml`, `producer.yaml` to point to `gcr.io/my-project/...`.

## 4. Autoscaling (HPA)
The Scaler handles *Job* scaling. But the Scaler itself or RabbitMQ might need scaling.
*   Use Standard K8s HPA for the `producer` API if traffic is high.

## 5. Deployment Commands
```bash
# 1. Apply Storage & Secrets
kubectl apply -f infra/pvc/
kubectl apply -f infra/secrets/

# 2. Apply Core Services (RabbitMQ, DB)
kubectl apply -f infra/k8s/rabbitmq.yaml
kubectl apply -f infra/k8s/postgres.yaml

# 3. Apply App
kubectl apply -f infra/k8s/scaler.yaml
kubectl apply -f infra/k8s/producer.yaml
kubectl apply -f infra/k8s/dashboard.yaml
```

## 6. Access
Get the LoadBalancer IP or Domain:
```bash
kubectl get ingress
```
Open `http://<your-domain>`
