import pika
import time
import os
import json
import socket
import datetime
import requests

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
SCALER_URL = os.getenv("SCALER_URL", "http://scaler:8000/report")
# Queue name comes from Env Var injected by Scaler
QUEUE_NAME = os.getenv("QUEUE_NAME", "spend_queue")
JOB_NAME = os.getenv("JOB_NAME", socket.gethostname()) 

def report_progress():
    try:
        # Report type explicitly
        payload = {"job_name": JOB_NAME, "processed": 1} 
        requests.post(SCALER_URL, json=payload, timeout=1)
    except Exception as e:
        print(f"Failed to report progress: {e}")

def callback(ch, method, properties, body):
    msg = body.decode()
    print(f"[Spend Analysis] Processing: {msg}")
    
    # Logic specific to Spend Analysis
    # Simulate data validation and categorization
    time.sleep(1) # Faster than translation
    print(f"[Spend Analysis] Categorizing expense... Done.")

    report_progress()
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print(f"Starting Spend Worker (Fixed Version) on queue: {QUEUE_NAME}")
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            break
        except Exception:
            time.sleep(5)

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    print(f" [*] Waiting for messages in {QUEUE_NAME}. To exit press CTRL+C")

    # Open persistent log file
    LOG_FILE = f"/logs/{JOB_NAME}.log"
    print(f"Logging to {LOG_FILE}")

    # Simple logger helper
    def log(msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        print(entry) # stdout for K8s
        try:
            with open(LOG_FILE, "a") as f:
                f.write(entry + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")

    def callback(ch, method, properties, body):
        start_time = time.time()
        start_str = time.strftime("%Y-%m-%d %H:%M:%S")

        data = json.loads(body)
        msg_id = data.get("message_id", "unknown")
        queued_at = data.get("queued_at", "unknown")

        log(f"Received message {msg_id}: {data}")

        # Simulate processing
        time.sleep(1)

        log(f"Processed message {msg_id}")

        # Calculate duration
        duration = int((time.time() - start_time) * 1000)
        end_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # Report to Scaler (Audit)
        try:
            report_payload = {
                "message_id": msg_id,
                "job_type": "spend-analysis", # Could be env var
                "worker_pod": JOB_NAME,
                "queued_at": queued_at,
                "picked_at": start_str,
                "processed_at": end_str,
                "duration_ms": duration,
                "status": "SUCCESS",
                "log_file": LOG_FILE
            }
            requests.post(SCALER_URL + "-message", json=report_payload, timeout=2) # Note: URL mismatch fix needed

            # Legacy Report (Progress)
            requests.post(SCALER_URL, json={"job_name": JOB_NAME, "processed": 1}, timeout=2)

        except Exception as e:
            log(f"Failed to report to scaler: {e}")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    main()
