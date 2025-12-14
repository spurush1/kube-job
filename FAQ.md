# FAQ & Common Debugging Guide

## 🔍 Logs & Observability

### "How do I see what the Scaler is doing?"
The Scaler is the brain. If scaling isn't working, check its logs first:
```bash
kubectl logs -l app=scaler -f
```
Look for lines like:
> `[spend-analysis] Queue: 0, Active: 10` (Indicates queue is empty, but jobs are still running)
> `Scaling down: Deleting idle job...`

### "How do I see the Worker's logs?"
You can use the **Dashboard** (click "Logs"), or use CLI:
```bash
# List all pods
kubectl get pods

# Tail logs of a specific worker
kubectl logs spend-analysis-x7312 -f
```

## ⚠️ Common Issues

### 1. "The Dashboard shows 'Network Error' or '500 Internal Server Error'"
*   **Cause**: The Backend (Scaler) might be crashing or the DB isn't ready.
*   **Fix**:
    1.  Check Scaler logs: `kubectl logs -l app=scaler`
    2.  If it says "relation users does not exist", the DB Init failed. Restart the scaler:
        ```bash
        ./platform/manage.sh up-backend
        ```

### 2. "I uploaded a file, but no jobs are starting!"
*   **Check 1**: Is the queue actually receiving messages?
    Run: `curl http://localhost:8000/stats -u admin:password`
    Look at `"queue_depth"`.
*   **Check 2**: Are you hitting the `MAX_JOBS` limit?
    The scaler won't spawn more than `MAX_JOBS` (default 3 or 10). Check `metrics['metrics']['max_jobs']`.
*   **Check 3**: Postgres Connection.
    If the worker cannot connect to Postgres to save the Audit Log, it might crash or hang. Check worker logs.

### 3. "Jobs are running but not processing anything (Idle)"
*   **Cause**: RabbitMQ queue might be empty, or the worker is crashed/stuck.
*   **Fix**:
    *   Check `kubectl get pods` status. If `Error` or `CrashLoopBackOff`, check logs.
    *   Check RabbitMQ UI (`http://localhost:15672`, user: `guest/guest`).

### 4. "Scaling Down is too slow!"
*   The system is designed to be conservative to prevent "flapping" (rapid up/down).
*   It requires **6 consecutive checks** (30 seconds) of zero queue + zero active processing before deleting a job.
*   This is controlled by `IDLE_THRESHOLD` in `scaler.py`.

## 🛠️ Infrastructure & Data

### "How do I connect to the Postgres Database directly?"
Since it's inside Kubernetes:
1.  Port forward Postgres:
    ```bash
    kubectl port-forward svc/postgres 5432:5432
    ```
2.  Connect with any SQL client (DBeaver, TablePlus, `psql`):
    *   Host: `localhost`
    *   Port: `5432`
    *   User: `postgres`
    *   Password: `password`
    *   DB: `platform`

### "How do I reset everything?"
If the system gets into a weird state (stuck jobs, bad DB data):
```bash
./platform/manage.sh down
# Wait a moment
./platform/manage.sh up
```
*Note: This deletes the DB volume ONLY if you deleted the PVC. `manage.sh down` usually keeps the volume. To FULLY wipe data, delete the PVC manually: `kubectl delete pvc postgres-pvc`.*

## ⚡ Cheat Sheet: Debugging Commands

### 1. Pod Status & Logs
```bash
# Check all pods status (Running, Pending, Error?)
kubectl get pods

# Check why a pod is stuck in Pending
kubectl describe pod <pod-name>

# Tail logs for the Scaler (The Brain)
kubectl logs -l app=scaler -f

# Tail logs for a specific Worker
kubectl logs -l type=spend-analysis -f --tail=100
```

### 2. Networking & Connectivity
```bash
# Test connection to Internal Scaler API
kubectl run curl-test --image=curlimages/curl -it --rm -- restart=Never -- curl http://scaler:8000/stats -u admin:password

# Forward RabbitMQ to access UI (if manage.sh is not running)
kubectl port-forward svc/rabbitmq 15672:15672
```

### 3. Database
```bash
# Enter the Postgres Pod
kubectl exec -it $(kubectl get pods -l app=postgres -o jsonpath="{.items[0].metadata.name}") -- bash

# Run SQL inside the pod
psql -U postgres -d platform -c "SELECT * FROM users;"
```

### 4. Restarting Specific Services
```bash
# Restart Scaler to reload config/code
kubectl rollout restart deployment scaler

# Restart all workers (delete them, Scaler will respawn if needed)
kubectl delete jobs -l app=worker-job
```
