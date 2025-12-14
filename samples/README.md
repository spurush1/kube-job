# Sample Workers

This directory contains reference implementations of Worker Jobs. Use these as templates for your own business logic.

## Available Samples

### 1. `worker-spend`
A "Spend Analysis" worker.
- **Language**: Python.
- **Logic**: Simulates processing financial data. Writes detailed audit logs.

### 2. `worker-trans`
A "Translation" worker.
- **Language**: Python.
- **Logic**: Simulates text translation (longer processing time).

### 3. `worker-complex`
A more structured example with separate modules.

## How to Create a New Worker

1. **Copy**: `cp -r worker-spend my-new-worker`.
2. **Edit**: Modify `main.py` with your logic.
   - **Important**: You must preserve the `report_message` logic to ensure the Platform can track your job!
3. **Build & Push**:
   ```bash
   ./push.sh my-new-worker purushsimhan/my-new-worker:latest
   ```

## 🔐 Authentication (Important)

### 1. To Push Images (Local)
You must be logged in to Docker Hub on your terminal.
```bash
docker login
# Enter username: purushsimhan
# Enter password: <your-token>
# (Generate token at: https://hub.docker.com/settings/security)
```
The `push.sh` script uses your local Docker credentials.

### 2. To Pull Images (Cluster)
For Kubernetes to run your private images, you must create a "Secret".

1. **Create the Secret**:
   ```bash
   kubectl create secret docker-registry my-hub-secret \
     --docker-server=https://index.docker.io/v1/ \
     --docker-username=purushsimhan \
     --docker-password=<your-token> \
     --docker-email=<your-email>
   ```

2. **Use the Secret**:
   Update `platform/jobs.config.json`:
   ```json
   "my-job": {
       ...
       "image": "purushsimhan/my-new-worker:latest",
       "pull_secret": "my-hub-secret"
   }
   ```

