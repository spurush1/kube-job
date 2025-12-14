# Platform Core

This directory contains the immutable core runtime of the Job Platform.

## Components

### 1. Scaler (`scaler/`)
The brain of the operation.
- **Role**: Monitors RabbitMQ queues and K8s API.
- **Logic**: Reads `jobs.config.json` and auto-scales Worker Jobs.
- **Audit**: Connects to Postgres to log every message lifecycle event.
- **API**: Exposes `POST /report-message` for workers and `GET /stats` for dashboard.

### 2. Producer (`producer/`)
The Generic Gateway.
- **Role**: Accepts `POST /submit/{job_type}`.
- **Logic**: Parses CSV/JSON, injects `message_id` + `queued_at`, and pushes to the correct RabbitMQ queue defined in config.

### 3. Dashboard (`dashboard/`)
The UI Layer.
- **Stack**: React + Vite + TailwindCSS.
- **Deployment**: Served via Nginx.
- **Features**: Real-time stats, Job filtering, Log viewing, Audit Trail.

### 4. Infrastructure (`infra/`)
Kubernetes Manifests.
- `rabbitmq.yaml`: Message Broker.
- `postgres.yaml`: Audit Database.
- `producer.yaml` / `scaler.yaml` / `dashboard.yaml`: Platform Services.

## Management
Use the `manage.sh` script to control the lifecycle:
```bash
./manage.sh up      # Deploy all
./manage.sh down    # Destroy all
./manage.sh forward # Access APIs
```
