FROM python:3.9-slim

WORKDIR /app

# Install system deps if needed
RUN pip install pika requests

# 1. Copy the module definition
COPY setup.py .
COPY my_business_logic/ my_business_logic/

# 2. Install it as a package
RUN pip install .

# 3. Copy the runner script
COPY runner.py .

CMD ["python", "-u", "runner.py"]
