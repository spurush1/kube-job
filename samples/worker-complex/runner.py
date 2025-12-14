import os
import pika
import json
import requests
from my_business_logic.processor import ComplexProcessor

# 1. Setup specific logic
processor = ComplexProcessor()

# 2. Setup Generic RabbitMQ / Scaler connection
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
SCALER_URL = os.getenv("SCALER_URL", "http://scaler:8000/report")
QUEUE_NAME = os.getenv("QUEUE_NAME", "complex_queue") 
JOB_NAME = os.getenv("JOB_NAME", "unknown")

def report_success():
    try:
        requests.post(SCALER_URL, json={"job_name": JOB_NAME, "processed": 1}, timeout=1)
    except:
        pass

def callback(ch, method, properties, body):
    msg = body.decode()
    
    # Delegate to module
    result = processor.process(msg)
    
    print(f"Result: {result}")
    
    report_success()
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print(f"Starting Modular Worker on {QUEUE_NAME}")
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    main()
