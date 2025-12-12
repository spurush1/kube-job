import pika
import time
import os
import uuid
import threading
import psutil
from kubernetes import client, config
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
import uvicorn
from pydantic import BaseModel

app = FastAPI()

# Global metrics
metrics = {
    "queue_depth": 0,
    "active_jobs": 0,
    "total_spawned": 0,
    "max_jobs": 0,
    "threshold": 0,
    "cpu_percent": 0,
    "memory_percent": 0,
    "total_consumed": 0
}

# Job history (simple in-memory list)
job_history = []
# Map to track processed count per job: {job_name: count}
job_processed_counts = {}
MAX_HISTORY = 50

class ReportRequest(BaseModel):
    job_name: str
    processed: int

@app.post("/report")
def report_progress(req: ReportRequest):
    metrics["total_consumed"] += req.processed
    if req.job_name in job_processed_counts:
        job_processed_counts[req.job_name] += req.processed
    else:
        job_processed_counts[req.job_name] = req.processed
    return {"status": "ok"}

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

def create_job():
    job_name = f"worker-job-{uuid.uuid4().hex[:6]}"
    
    # Define the job
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, labels={"app": "worker-job"}),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=60, # Cleanup after 60s
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "worker-job"}),
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
                            image="worker:latest", 
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
                                client.V1EnvVar(name="JOB_NAME", value=job_name)
                            ]
                        )
                    ]
                )
            )
        )
    )
    
    try:
        batch_v1.create_namespaced_job(body=job, namespace=NAMESPACE)
        print(f"Created job {job_name}")
        metrics["total_spawned"] += 1
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

def get_rabbitmq_stats():
    try:
        url = f"http://{RABBITMQ_HOST}:15672/api/queues/%2F/{QUEUE_NAME}"
        res = requests.get(url, auth=("guest", "guest"), timeout=2)
        if res.status_code == 200:
            data = res.json()
            ready = data.get("messages_ready", 0)
            unacked = data.get("messages_unacknowledged", 0)
            return ready, unacked
    except Exception as e:
        print(f"Error fetching RabbitMQ stats: {e}")
    return 0, 0

def scaler_loop():
    print("Scaler loop started...")
    idle_ticks = 0
    IDLE_THRESHOLD = 6 # 30 seconds (6 * 5s)
    
    while True:
        # fetch from API for more accurate unacked count
        ready, unacked = get_rabbitmq_stats()
        total_pending = ready + unacked
        
        active = get_active_jobs()
        measure_resources()
        
        # Update metrics
        metrics["queue_depth"] = ready 
        metrics["unacked"] = unacked
        metrics["active_jobs"] = active
        
        status = "Active"
        
        print(f"Queue: {ready} (Unacked: {unacked}), Active: {active}, CPU: {metrics['cpu_percent']}%, Mem: {metrics['memory_percent']}%")
        
        # Scale UP
        if ready > THRESHOLD and active < MAX_JOBS:
            count = 1
            # Burst scaling: If queue is huge (2x threshold), spawn more
            if ready > THRESHOLD * 2:
                # Spawn up to 5 workers, but don't exceed MAX_JOBS
                available_slots = MAX_JOBS - active
                count = min(5, available_slots)
                print(f"Threshold exceeded (Burst), spawning {count} worker jobs...")
            else:
                print("Threshold exceeded, spawning worker job...")

            for _ in range(count):
                create_job()
            
            idle_ticks = 0 
            status = f"Scaling Up (+{count})"
            
        # Scale DOWN
        elif total_pending == 0 and active > 0:
            idle_ticks += 1
            print(f"System idle (Queue=0, Unacked=0). Idle ticks: {idle_ticks}/{IDLE_THRESHOLD}")
            status = f"Idle ({idle_ticks}/{IDLE_THRESHOLD})"
            
            if idle_ticks >= IDLE_THRESHOLD:
                delete_job()
                idle_ticks = IDLE_THRESHOLD - 1 # Keep trying to delete one by one
                status = "Scaling Down"
        else:
            idle_ticks = 0
            
        metrics["status_msg"] = status
        time.sleep(POLL_INTERVAL)

@app.get("/stats")
def get_stats():
    return {
        "metrics": metrics,
        "jobs": job_history
    }

@app.get("/logs/{job_name}")
def get_logs(job_name: str):
    try:
        # Find pod associated with job
        pods = core_v1.list_namespaced_pod(
            NAMESPACE, 
            label_selector=f"job-name={job_name}"
        )
        if not pods.items:
            return "No pods found for this job yet."
            
        pod_name = pods.items[0].metadata.name
        logs = core_v1.read_namespaced_pod_log(pod_name, NAMESPACE)
        return PlainTextResponse(logs)
    except Exception as e:
        return PlainTextResponse(f"Error fetching logs: {str(e)}")

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
