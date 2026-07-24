FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data volume will be mounted at /data — point DB there via env var
ENV OLIN_DB_PATH=/data/olin_scoring.db
ENV OLIN_MODE=production

EXPOSE 8080

CMD ["python3", "-m", "olin.server", "--host", "0.0.0.0", "--port", "8080", "--db", "/data/olin_scoring.db", "--no-seed"]
