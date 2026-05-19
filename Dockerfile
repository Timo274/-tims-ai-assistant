FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY schema.sql ./schema.sql

RUN useradd --create-home --uid 1000 bot \
 && mkdir -p /app/data /app/logs \
 && chown -R bot:bot /app

USER bot

VOLUME ["/app/data", "/app/logs"]

CMD ["python", "-m", "bot"]
