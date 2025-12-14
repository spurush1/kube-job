import pika
import time
import os
import uuid
import json
import datetime
import threading
import psutil
from kubernetes import client, config
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

# Enable CORS for React Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Connection
DB_HOST = "postgres"
DB_NAME = "job_platform"
DB_USER = "user"
DB_PASS = "password"

def get_db_connection():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        return conn
    except Exception as e:
        print(f"DB Connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        # Job Audit Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS job_audit (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(50),
                job_type VARCHAR(50),
                status VARCHAR(20),
                spawned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)
        # Message Audit Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS message_audit (
                id SERIAL PRIMARY KEY,
                message_id VARCHAR(50),
                job_type VARCHAR(50),
                worker_pod VARCHAR(50),
                queued_at TIMESTAMP,
                picked_at TIMESTAMP,
                processed_at TIMESTAMP,
                duration_ms INT,
                status VARCHAR(20),
                log_file VARCHAR(255)
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Database schemas initialized.")
    except Exception as e:
        print(f"DB Init failed: {e}")

# Initialize DB on startup (in thread or before start)
init_db()

# Global metrics
metrics = {
    "queue_depth": 0,
    "active_jobs": 0,
    "total_spawned": 0,
    "max_jobs": 0,
    "threshold": 0,
    "cpu_percent": 0,
    "max_jobs": 0,
    "threshold": 0,
    "cpu_percent": 0,
    "memory_percent": 0,
    "total_consumed": 0,
    "avg_latency": 0,
    "throughput": 0
}

# Job history (simple in-memory list)
job_history = []
# Map to track processed count per job: {job_name: count}
job_processed_counts = {}
MAX_HISTORY = 50

class ReportRequest(BaseModel):
    # Backward compatibility
    job_name: str
    processed: int

class MessageReport(BaseModel):
    message_id: str
    job_type: str
    worker_pod: str
    queued_at: str
    picked_at: str
    processed_at: str
    duration_ms: int
    status: str
    log_file: str

@app.post("/report")
def report_progress(req: ReportRequest):
    metrics["total_consumed"] += req.processed
    if req.job_name in job_processed_counts:
        job_processed_counts[req.job_name] += req.processed
    else:
        job_processed_counts[req.job_name] = req.processed
    return {"status": "ok"}

@app.post("/report-message")
def report_message(msg: MessageReport):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO message_audit 
                (message_id, job_type, worker_pod, queued_at, picked_at, processed_at, duration_ms, status, log_file)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (msg.message_id, msg.job_type, msg.worker_pod, msg.queued_at, msg.picked_at, msg.processed_at, msg.duration_ms, msg.status, msg.log_file))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Failed to insert message audit: {e}")
    
    # Update metrics as well
    metrics["total_consumed"] += 1
    return {"status": "recorded"}

@app.get("/audit")
def get_audit(limit: int = 50):
    conn = get_db_connection()
    if not conn: return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM message_audit ORDER BY processed_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"Error fetching audit: {e}")
        return []

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "task_queue"
NAMESPACE = os.getenv("NAMESPACE", "default")
MAX_JOBS = int(os.getenv("MAX_JOBS", 3))
THRESHOLD = 20
POLL_INTERVAL = 5

metrics["max_jobs"] = MAX_JOBS
metrics["threshold"] = THRESHOLD

# Initialize K8s client
try:
    config.load_incluster_config()
except:
    config.load_kube_config()

batch_v1 = client.BatchV1Api()
core_v1 = client.CoreV1Api()

def get_queue_depth():
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        q = channel.queue_declare(queue=QUEUE_NAME, durable=True, passive=True)
        depth = q.method.message_count
        connection.close()
        return depth
    except Exception as e:
        print(f"Error checking queue: {e}")
        return 0

def get_active_jobs():
    jobs = batch_v1.list_namespaced_job(NAMESPACE, label_selector="app=worker-job")
    active_count = 0
    current_jobs = []
    
    for job in jobs.items:
        succeeded = job.status.succeeded or 0
        failed = job.status.failed or 0
        active = job.status.active or 0
        
        status = "Running"
        if succeeded > 0: status = "Succeeded"
        elif failed > 0: status = "Failed"
        
        if active > 0:
            active_count += 1
            
        start_time = job.status.start_time.strftime("%H:%M:%S") if job.status.start_time else "-"
        
        processed = job_processed_counts.get(job.metadata.name, 0)

        current_jobs.append({
            "name": job.metadata.name,
            "status": status,
            "start_time": start_time,
            "processed": processed
        })

    global job_history
    job_history = sorted(current_jobs, key=lambda x: x['start_time'], reverse=True)[:MAX_HISTORY]
    
    return active_count

def create_job(job_type, image):
    job_name = f"{job_type}-{uuid.uuid4().hex[:6]}"
    
    # Define the job
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, labels={"app": "worker-job", "type": job_type}),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=60, # Cleanup after 60s
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "worker-job", "type": job_type}),
                spec=client.V1PodSpec(
                    restart_policy="OnFailure",
                    volumes=[
                        client.V1Volume(
                            name="logs-volume",
                            host_path=client.V1HostPathVolumeSource(
                                path="/Users/purushsimhan/learning/kube-job/logs",
                                type="DirectoryOrCreate"
                            )
                        )
                    ],
                    containers=[
                        client.V1Container(
                            name="worker",
                            image=image, 
                            image_pull_policy="IfNotPresent",
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="logs-volume",
                                    mount_path="/logs"
                                )
                            ],
                            env=[
                                client.V1EnvVar(name="RABBITMQ_HOST", value=RABBITMQ_HOST),
                                client.V1EnvVar(name="SCALER_URL", value="http://scaler:8000/report"),
                                client.V1EnvVar(name="JOB_NAME", value=job_name),
                                client.V1EnvVar(name="JOB_TYPE", value=job_type),
                                client.V1EnvVar(name="QUEUE_NAME", value=JOB_CONFIG[job_type]["queue"])
                            ]
                        )
                    ],
                    image_pull_secrets=[client.V1LocalObjectReference(name=JOB_CONFIG[job_type].get("pull_secret"))] if JOB_CONFIG[job_type].get("pull_secret") else None
                )
            )
        )
    )
    
    try:
        batch_v1.create_namespaced_job(body=job, namespace=NAMESPACE)
        print(f"Created job {job_name}")
        metrics["total_spawned"] += 1
        
        # Audit Job Spawn
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO job_audit (job_id, job_type, status) VALUES (%s, %s, %s)", (job_name, job_type, "SPAWNED"))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Audit failed: {e}")
                
    except Exception as e:
        print(f"Failed to create job: {e}")

def delete_job():
    try:
        # Get list of jobs
        jobs = batch_v1.list_namespaced_job(NAMESPACE, label_selector="app=worker-job")
        if jobs.items:
            # Delete the oldest job
            job_to_delete = sorted(jobs.items, key=lambda x: x.metadata.creation_timestamp)[0]
            name = job_to_delete.metadata.name
            print(f"Scaling down: Deleting idle job {name}")
            batch_v1.delete_namespaced_job(
                name, 
                NAMESPACE, 
                body=client.V1DeleteOptions(propagation_policy='Background')
            )
            # Remove from processed counts to keep history clean? No, keep history.
    except Exception as e:
        print(f"Failed to delete job: {e}")

def measure_resources():
    metrics["cpu_percent"] = psutil.cpu_percent()
    metrics["memory_percent"] = psutil.virtual_memory().percent

import requests

# ... imports ...
CONFIG_PATH = "/app/config/jobs.config.json"

# Load Config with Env Var Expansion
try:
    with open(CONFIG_PATH, "r") as f:
        content = f.read()
        # Expand ${VAR} with environment variables
        content_expanded = os.path.expandvars(content)
        JOB_CONFIG = json.loads(content_expanded)["jobs"]
    print(f"Loaded job config with types: {list(JOB_CONFIG.keys())}")
except Exception as e:
    print(f"Failed to load job config: {e}")
    JOB_CONFIG = {}

# Global metrics (Updated to be a dict of dicts or aggregate?)
# For simplicity, we'll keep aggregate for top-level cards, but track details internally
metrics = {
    "queue_depth": 0,
    "unacked": 0,
    "active_jobs": 0,
    "status_msg": "Active",
    "cpu_percent": 0,
    "memory_percent": 0,
    "max_jobs": MAX_JOBS,
    "total_consumed": 0 # Aggregate
}
# We need detailed state for each job type to manage scaling independently
# type_state = { "spend-analysis": { "idle_ticks": 0, ... } }
type_state = {}

def get_rabbitmq_stats(queue_name):
    try:
        url = f"http://{RABBITMQ_HOST}:15672/api/queues/%2F/{queue_name}"
        res = requests.get(url, auth=("guest", "guest"), timeout=2)
        if res.status_code == 200:
            data = res.json()
            ready = data.get("messages_ready", 0)
            unacked = data.get("messages_unacknowledged", 0)
            return ready, unacked
    except Exception as e:
        print(f"Error fetching RabbitMQ stats for {queue_name}: {e}")
    return 0, 0

def update_job_history_and_counts():
    """
    Fetches all worker jobs, updates global job_history for the dashboard,
    and returns a dictionary of active job counts per type.
    """
    try:
        # Fetch ALL worker jobs regardless of type
        jobs = batch_v1.list_namespaced_job(NAMESPACE, label_selector="app=worker-job")
        
        current_jobs = []
        type_counts = {jt: 0 for jt in JOB_CONFIG.keys()}
        
        for job in jobs.items:
            # Metadata
            name = job.metadata.name
            jtype = job.metadata.labels.get("type", "unknown")
            
            # Status
            succeeded = job.status.succeeded or 0
            failed = job.status.failed or 0
            active = job.status.active or 0
            
            status = "Running"
            if succeeded > 0: status = "Succeeded"
            elif failed > 0: status = "Failed"
            
            # Count active for scaling logic
            if active > 0 and jtype in type_counts:
                type_counts[jtype] += 1
            
            # Dashboard Data
            start_time = job.status.start_time.strftime("%H:%M:%S") if job.status.start_time else "-"
            # We might need a way to track processed count per job. 
            # Ideally this comes from the worker report. 
            # For now, let's just use what we have in the global dict if we persisted it, 
            # or rely on reports updating a global 'job_processed_counts' dict.
            # We need to make sure job_processed_counts is defined globally.
            processed = job_processed_counts.get(name, 0)

            current_jobs.append({
                "name": name,
                "type": jtype, # Add type to dashboard?
                "status": status,
                "start_time": start_time,
                "processed": processed
            })

        global job_history
        # Sort by start time desc
        job_history = sorted(current_jobs, key=lambda x: x['start_time'], reverse=True)[:MAX_HISTORY]
        
        return type_counts
        
    except Exception as e:
        print(f"Error listing jobs: {e}")
        return {jt: 0 for jt in JOB_CONFIG.keys()}

def scaler_loop():
    print("Scaler loop started...")
    
    # Initialize state
    for jt in JOB_CONFIG:
        type_state[jt] = {"idle_ticks": 0}

    IDLE_THRESHOLD = 6
    
    while True:
        # 1. Fetch ALL k8s state once
        active_counts = update_job_history_and_counts()
        measure_resources()
        
        # 2. Aggregates for top-level cards
        total_depth = 0
        total_unacked = 0
        total_active = sum(active_counts.values())
        
        # 3. Iterate Types
        for job_type, config in JOB_CONFIG.items():
            queue_name = config["queue"]
            image = config["image"]
            threshold = config["threshold"]
            
            ready, unacked = get_rabbitmq_stats(queue_name)
            pending = ready + unacked
            active = active_counts.get(job_type, 0)
            
            total_depth += ready
            total_unacked += unacked
            
            # Logic
            print(f"[{job_type}] Queue: {ready}, Active: {active}")
            
            # Scale UP
            if ready > threshold and active < MAX_JOBS: 
                 # Simple logic: if over threshold, spawn.
                 # Burst logic:
                 count = 1
                 if ready > threshold * 2:
                     count = min(5, MAX_JOBS - total_active) # Shared pool limit check (rough)
                     # If total_active is high, we might not be able to burst.
                 
                 # Safety: explicit max per type check? 
                 # Let's trust K8s pending state for now.
                 
                 if count > 0:
                     print(f"Spawning {count} workers for {job_type}")
                     for _ in range(count): create_job(job_type, image)
                     type_state[job_type]["idle_ticks"] = 0
            
            # Scale DOWN
            elif pending == 0 and active > 0:
                type_state[job_type]["idle_ticks"] += 1
                if type_state[job_type]["idle_ticks"] >= IDLE_THRESHOLD:
                     delete_job(job_type)
                     type_state[job_type]["idle_ticks"] = IDLE_THRESHOLD - 1
            else:
                type_state[job_type]["idle_ticks"] = 0

        # 4. Advanced Metrics from DB
        conn = get_db_connection()
        avg_latency = 0
        throughput = 0
        if conn:
            try:
                cur = conn.cursor()
                # Avg Latency (last 10 mins)
                cur.execute("SELECT AVG(duration_ms) FROM message_audit WHERE processed_at > NOW() - INTERVAL '10 minutes'")
                res = cur.fetchone()
                if res and res[0] is not None:
                    avg_latency = round(res[0], 2)
                    
                # Throughput RPM (last 1 min)
                cur.execute("SELECT COUNT(*) FROM message_audit WHERE processed_at > NOW() - INTERVAL '1 minute'")
                res = cur.fetchone()
                if res:
                    throughput = res[0]
                    
                cur.close()
                conn.close()
            except Exception as e:
                print(f"Metrics calc failed: {e}")

        # Update Global Metrics
        metrics["queue_depth"] = total_depth
        metrics["unacked"] = total_unacked
        metrics["active_jobs"] = total_active
        metrics["avg_latency"] = avg_latency
        metrics["throughput"] = throughput
        metrics["status_msg"] = "Running"
        
        time.sleep(POLL_INTERVAL)

@app.get("/stats")
def get_stats():
    return {
        "metrics": metrics,
        "jobs": job_history
    }

@app.get("/logs/{job_name}")
def get_logs(job_name: str, since_minutes: int = 0):
    try:
        # Find pod associated with job
        pods = core_v1.list_namespaced_pod(
            NAMESPACE, 
            label_selector=f"job-name={job_name}"
        )
        if not pods.items:
            return "No pods found for this job yet."
            
        pod_name = pods.items[0].metadata.name
        
        # Calculate trailing seconds
        since_seconds = None
        if since_minutes > 0:
            since_seconds = since_minutes * 60
            
        logs = core_v1.read_namespaced_pod_log(
            pod_name, 
            NAMESPACE,
            since_seconds=since_seconds
        )
        return PlainTextResponse(logs)
    except Exception as e:
        return PlainTextResponse(f"Error fetching logs: {str(e)}")

@app.get("/audit/log")
def get_audit_log(file_path: str):
    # Security check: ensure path is within /logs to prevent traversal
    safe_base = "/logs"
    if not file_path.startswith(safe_base) and not file_path.startswith("/logs"):
         # Handle case where file_path passed is just filename or relative
         file_path = os.path.join(safe_base, os.path.basename(file_path))
    
    # Also handle full path if passed as /logs/...
    if not os.path.abspath(file_path).startswith(safe_base):
        return PlainTextResponse("Access Denied: Invalid log path", status_code=403)

    if not os.path.exists(file_path):
        return PlainTextResponse(f"Log file not found: {file_path}", status_code=404)

    try:
        with open(file_path, "r") as f:
            return PlainTextResponse(f.read())
    except Exception as e:
        return PlainTextResponse(f"Failed to read log file: {e}", status_code=500)

@app.get("/cluster-info")
def get_cluster_info():
    try:
        # Nodes
        nodes = core_v1.list_node().items
        node_data = []
        for n in nodes:
            node_data.append({
                "name": n.metadata.name,
                "status": "Ready" if n.status.conditions[-1].type == "Ready" and n.status.conditions[-1].status == "True" else "NotReady",
                "cpu": n.status.capacity.get("cpu"),
                "memory": n.status.capacity.get("memory"),
                "os": n.status.node_info.os_image,
                "kernel": n.status.node_info.kernel_version
            })

        # Events
        events = core_v1.list_namespaced_event(NAMESPACE).items
        # Sort by timestamp desc
        sorted_events = sorted(events, key=lambda e: e.last_timestamp or e.event_time or e.first_timestamp or datetime.datetime.min, reverse=True)[:20]
        event_data = [{
            "type": e.type,
            "reason": e.reason,
            "message": e.message,
            "object": e.involved_object.kind + "/" + e.involved_object.name,
            "time": (e.last_timestamp or e.event_time).strftime("%H:%M:%S") if (e.last_timestamp or e.event_time) else "-"
        } for e in sorted_events]

        # All Pods (for detailed view)
        all_pods = core_v1.list_namespaced_pod(NAMESPACE).items
        pod_data = [{
            "name": p.metadata.name,
            "status": p.status.phase,
            "ip": p.status.pod_ip,
            "node": p.spec.node_name,
            "restarts": sum(c.restart_count for c in p.status.container_statuses) if p.status.container_statuses else 0
        } for p in all_pods]

        return {
            "nodes": node_data,
            "events": event_data,
            "pods": pod_data
        }
    except Exception as e:
        print(f"Cluster info failed: {e}")
        return {"nodes": [], "events": [], "pods": [], "error": str(e)}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>K8s Scaler Dashboard</title>
        <style>
            :root { --primary: #2563eb; --bg: #f8fafc; --card: #ffffff; --text: #1e293b; }
            body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: var(--bg); color: var(--text); }
            .container { max-width: 1200px; margin: 0 auto; }
            
            h1 { font-size: 1.5rem; margin-bottom: 20px; color: var(--primary); display: flex; align-items: center; gap: 10px; }
            
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .card { background: var(--card); padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
            .card-label { font-size: 0.875rem; color: #64748b; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.05em; }
            .card-value { font-size: 2rem; font-weight: 700; color: var(--text); }
            .card-sub { font-size: 0.8rem; color: #94a3b8; margin-top: 5px; }

            .table-container { background: var(--card); border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; }
            table { width: 100%; border-collapse: collapse; text-align: left; }
            th { background: #f1f5f9; padding: 12px 20px; font-weight: 600; font-size: 0.875rem; color: #475569; }
            td { padding: 12px 20px; border-bottom: 1px solid #e2e8f0; font-size: 0.9rem; }
            tr:last-child td { border-bottom: none; }
            tr:hover { background: #f8fafc; }
            
            .status-badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
            .status-Running { background: #dbeafe; color: #1d4ed8; }
            .status-Succeeded { background: #dcfce7; color: #15803d; }
            .status-Failed { background: #fee2e2; color: #b91c1c; }
            
            .btn { background: var(--primary); color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; transition: opacity 0.2s; }
            .btn:hover { opacity: 0.9; }

            /* Modal */
            .modal { display: none; position: fixed; top: 0; left: 0; w-100; h-100; width: 100%; height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 1000; }
            .modal-content { background: white; width: 80%; max-width: 800px; height: 80%; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; }
            .modal-header { display: flex; justify-content: space-between; margin-bottom: 15px; }
            .close-btn { background: none; border: none; font-size: 1.5rem; cursor: pointer; }
            .log-box { flex: 1; background: #1e293b; color: #e2e8f0; font-family: monospace; padding: 15px; border-radius: 8px; overflow: auto; white-space: pre-wrap; font-size: 0.9rem; }
            
            .system-status { font-size: 0.9rem; color: #64748b; margin-left: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                📊 Job Scaler Dashboard
                <span class="system-status" id="system_status">Initializing...</span>
            </h1>
            
            <!-- Cards -->
            <div class="grid">
                <div class="card">
                    <div class="card-label">Queue Depth</div>
                    <div class="card-value" id="queue_depth">-</div>
                    <div class="card-sub">Messages Pending</div>
                </div>
                <div class="card">
                    <div class="card-label">Unacknowledged</div>
                    <div class="card-value" id="unacked">-</div>
                    <div class="card-sub">Processing Now</div>
                </div>
                <div class="card">
                    <div class="card-label">Active Jobs</div>
                    <div class="card-value"><span id="active_jobs">-</span> <span style="font-size:1rem; color:#94a3b8">/ <span id="max_jobs">-</span></span></div>
                    <div class="card-sub">Running Workers</div>
                </div>
                <div class="card">
                    <div class="card-label">Total Consumed</div>
                    <div class="card-value" id="total_consumed">-</div>
                    <div class="card-sub">Messages Processed</div>
                </div>
                <div class="card">
                    <div class="card-label">System Load</div>
                    <div class="card-value"><span id="cpu_val">-</span>%</div>
                    <div class="card-sub">Mem: <span id="mem_val">-</span>%</div>
                </div>
            </div>

            <!-- Table -->
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Job Name</th>
                            <th>Status</th>
                            <th>Start Time</th>
                            <th>Processed</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="job_table_body">
                        <!-- Rows injected by JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Log Modal -->
        <div class="modal" id="logModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 style="margin:0; font-size:1.2rem;">Job Logs: <span id="modalJobName">...</span></h2>
                    <button class="close-btn" onclick="closeModal()">&times;</button>
                </div>
                <div class="log-box" id="logContent">Loading...</div>
            </div>
        </div>

        <script>
            async function refresh() {
                try {
                    const res = await fetch('/stats');
                    const data = await res.json();
                    const m = data.metrics;
                    
                    // Update Cards
                    document.getElementById('queue_depth').innerText = m.queue_depth;
                    document.getElementById('unacked').innerText = m.unacked || 0;
                    document.getElementById('active_jobs').innerText = m.active_jobs;
                    document.getElementById('max_jobs').innerText = m.max_jobs;
                    document.getElementById('total_consumed').innerText = m.total_consumed || 0;
                    document.getElementById('cpu_val').innerText = m.cpu_percent;
                    document.getElementById('mem_val').innerText = m.memory_percent;
                    document.getElementById('system_status').innerText = m.status_msg || "Active";

                    // Update Table
                    const tbody = document.getElementById('job_table_body');
                    tbody.innerHTML = data.jobs.map(job => `
                        <tr>
                            <td>${job.name}</td>
                            <td><span class="status-badge status-${job.status}">${job.status}</span></td>
                            <td>${job.start_time}</td>
                            <td><strong>${job.processed || 0}</strong></td>
                            <td><button class="btn" onclick="viewLogs('${job.name}')">View Logs</button></td>
                        </tr>
                    `).join('');

                } catch(e) { console.error("Fetch error:", e); }
            }

            async function viewLogs(jobName) {
                const modal = document.getElementById('logModal');
                const content = document.getElementById('logContent');
                document.getElementById('modalJobName').innerText = jobName;
                modal.style.display = 'flex';
                content.innerText = 'Fetching logs...';
                
                try {
                    const res = await fetch(`/logs/${jobName}`);
                    const text = await res.text();
                    content.innerText = text;
                } catch(e) {
                    content.innerText = "Failed to load logs.";
                }
            }

            function closeModal() {
                document.getElementById('logModal').style.display = 'none';
            }

            // Close modal on outside click
            window.onclick = function(event) {
                const modal = document.getElementById('logModal');
                if (event.target == modal) {
                    modal.style.display = "none";
                }
            }

            setInterval(refresh, 2000);
            refresh();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    t = threading.Thread(target=scaler_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
