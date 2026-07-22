FROM python:3.12-slim
WORKDIR /opt/aruba-ingestion
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python", "-m", "app.scheduler"]
