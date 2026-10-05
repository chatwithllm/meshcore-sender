FROM python:3.11-slim-bookworm

ARG SENDER_REF=0b78351eb97c68e66b07ca4df1f8e1d48a461b89
ADD https://github.com/chatwithllm/meshcore-sender/archive/${SENDER_REF}.tar.gz /tmp/sender.tar.gz
RUN mkdir /app && tar -xzf /tmp/sender.tar.gz -C /app --strip-components=1 && \
    rm /tmp/sender.tar.gz && \
    pip install --no-cache-dir meshcore==2.3.14 meshcore-cli==1.6.4

ENV PYTHONUNBUFFERED=1 MESHCORE_HOST=0.0.0.0 PORT=8788 DATA_DIR=/data
WORKDIR /app
COPY run.py /app/run_homeassistant.py
CMD ["python", "/app/run_homeassistant.py"]
