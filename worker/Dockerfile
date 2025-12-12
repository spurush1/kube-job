FROM python:3.9-slim

WORKDIR /app

RUN pip install pika requests

COPY worker.py .

# Force python to not buffer output so logs appear in K8s immediately
ENV PYTHONUNBUFFERED=1

CMD ["python", "worker.py"]
