FROM python:3.9-slim

WORKDIR /app

RUN pip install pika requests

COPY main.py .

CMD ["python", "-u", "main.py"]
