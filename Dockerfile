FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt

RUN groupadd --system olin && useradd --system --gid olin --home-dir /app olin \
    && mkdir -p /data && chown olin:olin /data

COPY --chown=olin:olin . .

ENV OLIN_MODE=production

EXPOSE 8080

USER olin

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2)"]

CMD ["python3", "-m", "olin.server", "--host", "0.0.0.0", "--port", "8080", "--no-seed", "--no-open"]
