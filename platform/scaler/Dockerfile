FROM python:3.9-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN pip install pika kubernetes fastapi uvicorn psutil requests psycopg2-binary

COPY scaler.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "scaler.py"]
