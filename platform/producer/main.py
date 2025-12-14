
import os
import json
import csv
import io
import uuid
import time
from fastapi import FastAPI, UploadFile, File, HTTPException
import pika.exceptions

app = FastAPI()

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
CONFIG_PATH = "/app/config/jobs.config.json"

# Load Config
try:
    with open(CONFIG_PATH, "r") as f:
        JOB_CONFIG = json.load(f)["jobs"]
    print(f"Loaded job config with types: {list(JOB_CONFIG.keys())}")
except Exception as e:
    print(f"Failed to load job config: {e}")
    JOB_CONFIG = {}

def get_channel(queue_name):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    return connection, channel

@app.post("/submit/{job_type}")
async def submit_job(job_type: str, file: UploadFile = File(...)):
    if job_type not in JOB_CONFIG:
        raise HTTPException(status_code=404, detail=f"Job type '{job_type}' not found. Available: {list(JOB_CONFIG.keys())}")

    config = JOB_CONFIG[job_type]
    queue_name = config["queue"]

    content = await file.read()
    decoded = content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(decoded))
    
    count = 0
    try:
        connection, channel = get_channel(queue_name)
        
        for row in csv_reader:
            # Inject Traceability Data
            row["message_id"] = str(uuid.uuid4())
            row["queued_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            message = json.dumps(row)
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                ))
            count += 1
            
        connection.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": f"Processed {count} rows for job '{job_type}' and pushed to '{queue_name}'"}
