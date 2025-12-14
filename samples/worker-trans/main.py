import pika
import time
import os
import json
import socket
import datetime
import requests

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
SCALER_URL = os.getenv("SCALER_URL", "http://scaler:8000/report")
QUEUE_NAME = os.getenv("QUEUE_NAME", "translation_queue") 

def report_progress():
    try:
        job_name = os.getenv("JOB_NAME", socket.gethostname())
        payload = {"job_name": job_name, "processed": 1}
        requests.post(SCALER_URL, json=payload, timeout=1)
    except Exception as e:
        print(f"Failed to report progress: {e}")

def callback(ch, method, properties, body):
    msg = body.decode()
    print(f"[Translation] Translating fragment: {msg[:20]}...")
    
    # Logic specific to Translation
    # Simulate heavy neural network inference
    time.sleep(3) # Slower task
    print(f"[Translation] Model inference complete.")
    
    report_progress()
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print(f"Starting Translation Worker on queue: {QUEUE_NAME}")
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            break
        except Exception:
            time.sleep(5)
    
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    main()
