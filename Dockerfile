FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV HOST=0.0.0.0 \
    PORT=8080 \
    SCAN_DATA_DIR=/data/scans
RUN mkdir -p /data/scans
EXPOSE 8080
CMD ["scan-api"]
