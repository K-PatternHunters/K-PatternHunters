FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transform.py .
COPY export_bq.py .
COPY ingest_local.py .

CMD ["echo", "Usage: python export_bq.py  |  python ingest_local.py"]