FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8788 \
    DATA_DIR=/data \
    MESHCORE_TIMEOUT=30

WORKDIR /app

RUN python -m pip install --no-cache-dir meshcore-cli

COPY src /app/src
COPY public /app/public

RUN useradd --create-home --uid 10001 meshcore && \
    mkdir -p /data && \
    chown -R meshcore:meshcore /data /app

USER meshcore
VOLUME ["/data"]
EXPOSE 8788

CMD ["python", "src/server.py"]
