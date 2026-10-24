FROM python:3.12-slim
WORKDIR /opt/aruba-ingestion
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-query.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS}
COPY app ./app
CMD ["python", "-m", "app.worker"]
