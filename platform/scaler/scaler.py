import pika
import time
import os
import uuid
import json
import datetime
import threading
import psutil
from kubernetes import client, config
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import secrets
import hashlib
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

@app.on_event("startup")
def startup_event():
    t = threading.Thread(target=scaler_loop, daemon=True)
    t.start()
    print("Background scaler loop started.")

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
    retries = 10
    while retries > 0:
        try:
            conn = get_db_connection()
            if not conn:
                print("DB connection failed, retrying...")
                retries -= 1
                time.sleep(3)
                continue
                
            cur = conn.cursor()
            # Create Audit Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_audit (
                    id SERIAL PRIMARY KEY,
                    message_id VARCHAR(50),
                    job_type VARCHAR(50),
                    worker_pod VARCHAR(50),
                    queued_at TIMESTAMP,
                    picked_at TIMESTAMP,
                    processed_at TIMESTAMP,
                    duration_ms INTEGER,
                    status VARCHAR(20),
                    log_file VARCHAR(200)
                );
            """)
            # Create Job Audit
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_audit (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(50),
                    job_type VARCHAR(50),
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            cur.close()
            # Ensure Users Setup
            seed_users(conn)
            conn.close()
            print("Database schemas initialized.")
            return
        except Exception as e:
            print(f"DB Init failed: {e}, retrying in 3s...")
            retries -= 1
            time.sleep(3)
    print("CRITICAL: Failed to initialize DB after retries.")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def seed_users(conn):
    try:
        cur = conn.cursor()
        # Create Users Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                password_hash VARCHAR(64) NOT NULL
            );
        """)
        # Check if admin exists
        cur.execute("SELECT count(*) FROM users WHERE username = %s", ("admin",))
        count = cur.fetchone()[0]
        if count == 0:
            p_hash = hash_password("password")
            cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", ("admin", p_hash))
            conn.commit()
            print("Seeded default admin user.")
        cur.close()
    except Exception as e:
        print(f"User seeding failed: {e}")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "task_queue"
NAMESPACE = os.getenv("NAMESPACE", "default")
MAX_JOBS = int(os.getenv("MAX_JOBS", 3))
THRESHOLD = 20
POLL_INTERVAL = 5

CONFIG_PATH = "/app/config/jobs.config.json"

JOB_CONFIG = {}

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
# We need detailed state for each job type to manage scaling independently
# type_state = { "spend-analysis": { "idle_ticks": 0, ... } }
type_state = {}

security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable for auth",
        )
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = %s", (credentials.username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            # User not found
            # Use constant time comparison to mitigate timing attacks even on failure (mock comparison)
            secrets.compare_digest("invalid", "invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Basic"},
            )
            
        stored_hash = row[0]
        provided_hash = hash_password(credentials.password)
        
        if not secrets.compare_digest(stored_hash, provided_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Basic"},
            )
            
        return credentials.username
        
    except Exception as e:
        print(f"Auth error: {e}")
        if conn: conn.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed internally",
        )

def get_rabbitmq_stats(queue_name):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        # Declare the queue passively to get its properties
        q_declare_ok = channel.queue_declare(queue=queue_name, durable=True, passive=True)
        
        messages_in_queue = q_declare_ok.method.message_count
        messages_unacked = 0 # q_declare_ok.method.consumer_count is consumers, not unacked. Default to 0 without mgmt api.
        
        connection.close()
        return messages_in_queue, messages_unacked
    except pika.exceptions.ChannelClosedByBroker:
        print(f"Queue '{queue_name}' does not exist.")
        return 0, 0
    except Exception as e:
        print(f"Error getting RabbitMQ stats for queue {queue_name}: {e}")
        return 0, 0

# Initialize DB on startup (in thread or before start)
init_db()

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

def delete_job(job_type=None):
    try:
        # Get list of jobs
        label_selector = "app=worker-job"
        if job_type:
            label_selector += f",type={job_type}"
            
        jobs = batch_v1.list_namespaced_job(NAMESPACE, label_selector=label_selector)
        if jobs.items:
            # Filter for ACTIVE jobs that are NOT already terminating
            candidates = [
                j for j in jobs.items 
                if (j.status is not None and j.status.active is not None and j.status.active > 0)
                and j.metadata.deletion_timestamp is None
            ]
            
            if not candidates:
                print(f"No active, non-terminating jobs to delete for {job_type}")
                return

            # Delete the oldest job
            job_to_delete = sorted(candidates, key=lambda x: x.metadata.creation_timestamp)[0]
            name = job_to_delete.metadata.name
            print(f"Scaling down: Deleting idle job {name}")
            batch_v1.delete_namespaced_job(
                name, 
                NAMESPACE, 
                body=client.V1DeleteOptions(propagation_policy='Background')
            )
    except Exception as e:
        print(f"Failed to delete job: {e}")

# ... (rest of file)

# ... imports ...

def measure_resources():
    metrics["cpu_percent"] = psutil.cpu_percent()
    metrics["memory_percent"] = psutil.virtual_memory().percent

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
            
            # Count active/occupying for scaling logic
            # Fix: Count ANY job that hasn't succeeded or failed as "Active" 
            # (including Pending jobs that haven't spun up a pod yet)
            is_occupying_slot = (succeeded == 0 and failed == 0)
            
            if is_occupying_slot and jtype in type_counts:
                type_counts[jtype] += 1
            
            # Dashboard Data
            start_time = job.status.start_time.strftime("%H:%M:%S") if job.status.start_time else "-"
            processed = job_processed_counts.get(name, 0)
            
            # Update status string for dashboard if it's pending (active=0 but occupy=True)
            if status == "Running" and active == 0:
                status = "Pending"

            current_jobs.append({
                "name": name,
                "type": jtype,
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
        try:
            # 1. Fetch ALL k8s state once
            # Optimization: Instead of querying K8s for each job type, we list ALL jobs once.
            active_counts = update_job_history_and_counts()
            measure_resources()
            
            # 2. Aggregates for top-level cards
            total_depth = 0
            total_unacked = 0
            total_active = sum(active_counts.values())
            
            # 3. Iterate Types (The Core Scaling Logic)
            for job_type, config in JOB_CONFIG.items():
                queue_name = config["queue"]
                image = config["image"]
                threshold = config["threshold"]
                
                # Get Queue Stats from RabbitMQ
                ready, unacked = get_rabbitmq_stats(queue_name)
                pending = ready + unacked
                active = active_counts.get(job_type, 0)
                
                total_depth += ready
                total_unacked += unacked
                
                # Logic
                print(f"[{job_type}] Queue: {ready}, Active: {active}")
                
                # Scale UP Condition
                # If queue has messages AND we haven't hit the limit
                if ready > threshold and active < MAX_JOBS: 
                     # Burst logic: If lag is high, spawn multiple workers at once
                     count = 1
                     if ready > threshold * 2:
                         count = min(5, MAX_JOBS - total_active) # Shared pool limit check (rough)
                     
                     if count > 0:
                         print(f"Spawning {count} workers for {job_type}")
                         for _ in range(count): create_job(job_type, image)
                         type_state[job_type]["idle_ticks"] = 0
                
                # Scale DOWN Condition (Delete Idle Jobs)
                # If queue is empty AND no messages are being processed (pending includes unacked)
                elif pending == 0 and active > 0:
                    type_state[job_type]["idle_ticks"] += 1
                    # Require multiple consecutive idle checks to prevent flapping
                    if type_state[job_type]["idle_ticks"] >= IDLE_THRESHOLD:
                         delete_job(job_type) # Deletes only one job per interval
                         type_state[job_type]["idle_ticks"] = IDLE_THRESHOLD - 1
                else:
                    # Reset idle counter if busy
                    type_state[job_type]["idle_ticks"] = 0

            # 4. Advanced Metrics from DB (Calculated in background)
            # This fetches throughput and latency from the Postgres Audit Log
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
            
            # Update Scaling Status for UI
            scaling_status = {}
            for jt, state in type_state.items():
                idle_ticks = state.get("idle_ticks", 0)
                idle_seconds = idle_ticks * POLL_INTERVAL
                # Time to scale down = (Threshold - Ticks) * Interval
                # If ticks >= threshold, it's 0 (job being deleted)
                remaining_ticks = max(0, IDLE_THRESHOLD - idle_ticks)
                scale_down_in = remaining_ticks * POLL_INTERVAL
                
                # Check if actually idle (metrics logic might need to pass this through)
                # We can re-check the 'pending' state or trust the loop's local variables if we move this inside
                # For now, let's just use the state we have.  NOTE: We need 'active' count here too.
                # Since 'active_counts' is available in the loop, we should construct this inside the loop or make active_counts global.
                # Let's trust active_counts from this iteration.
                
                scaling_status[jt] = {
                    "active": active_counts.get(jt, 0),
                    "idle_seconds": idle_seconds if idle_ticks > 0 else 0,
                    "scale_down_in": scale_down_in if idle_ticks > 0 else 0,
                    "is_idle": idle_ticks > 0
                }
            metrics["scaling_status"] = scaling_status
            
        except Exception as e:
            print(f"Scaler loop error: {e}")
            metrics["status_msg"] = "Error"
        
        time.sleep(POLL_INTERVAL)

@app.get("/stats")
def get_stats(username: str = Depends(get_current_username)):
    return {
        "metrics": metrics,
        "jobs": job_history
    }

@app.get("/logs/{job_name}")
def get_logs(job_name: str, since_minutes: int = 0, username: str = Depends(get_current_username)):
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
def get_audit_log(file_path: str, username: str = Depends(get_current_username)):
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
def get_cluster_info(username: str = Depends(get_current_username)):
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

# Legacy Dashboard Removed
# Use React Dashboard on port 9090

if __name__ == "__main__":
    t = threading.Thread(target=scaler_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
