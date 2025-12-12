FROM python:3.9-slim

WORKDIR /app

RUN pip install pika kubernetes fastapi uvicorn psutil requests

COPY scaler.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "scaler.py"]
