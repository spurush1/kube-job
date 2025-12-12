from fastapi import FastAPI, UploadFile, File
import pika
import csv
import io
import time
import os

app = FastAPI()

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "task_queue"

def get_rabbitmq_channel():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    return connection, channel

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "Only CSV files are allowed"}

    content = await file.read()
    decoded_content = content.decode("utf-8")
    csv_reader = csv.reader(io.StringIO(decoded_content))
    
    # Skip header
    next(csv_reader, None)

    connection, channel = get_rabbitmq_channel()
    
    count = 0
    for row in csv_reader:
        message = ",".join(row)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ))
        count += 1
        
        # Throttling: Halt for 1 sec for each 10 messages
        if count % 10 == 0:
            time.sleep(1)

    connection.close()
    return {"message": f"Processed {count} rows and pushed to {QUEUE_NAME}"}
