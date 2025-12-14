import pika
import time
import os
import json
import socket
import datetime
import sys

import requests

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
SCALER_URL = os.getenv("SCALER_URL", "http://scaler:8000/report")
QUEUE_NAME = "task_queue"
LOG_FILE = "/logs/worker.log"

def log_event(event_type, details):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "worker_id": socket.gethostname(),
        "event": event_type,
        "details": details
    }
    log_line = json.dumps(entry)
    print(log_line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

def report_progress():
    try:
        job_name = os.getenv("JOB_NAME", socket.gethostname())
        payload = {"job_name": job_name, "processed": 1}
        requests.post(SCALER_URL, json=payload, timeout=1)
    except Exception as e:
        print(f"Failed to report progress: {e}")

def callback(ch, method, properties, body):
    msg = body.decode()
    log_event("START_PROCESSING", {"message": msg, "delivery_tag": method.delivery_tag})
    
    # Simulating processing time
    time.sleep(2)
    
    log_event("END_PROCESSING", {"message": msg, "delivery_tag": method.delivery_tag})
    report_progress()
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    log_event("WORKER_START", {})
    # Add a retry mechanism for startup race conditions
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            break
        except Exception as e:
            print(f"Waiting for RabbitMQ... {e}")
            time.sleep(5)
    
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

    log_event("WORKER_READY", {"queue": QUEUE_NAME})
    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == "__main__":
    main()
