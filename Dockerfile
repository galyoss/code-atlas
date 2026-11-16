FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates curl unzip bash \
    && rm -rf /var/lib/apt/lists/*

# Temurin 21 JRE. Joern's launchers use JAVA_HOME or java on PATH.
ARG TEMURIN_JRE_URL=https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jre_x64_linux_hotspot_21.0.13_9.tar.gz
RUN curl -fsSL --retry 3 --retry-delay 2 -o /tmp/jre.tar.gz "$TEMURIN_JRE_URL" \
    && mkdir -p /opt/java \
    && tar -xzf /tmp/jre.tar.gz -C /opt/java --strip-components=1 \
    && rm /tmp/jre.tar.gz

ENV JAVA_HOME=/opt/java
ENV PATH="/opt/java/bin:${PATH}"

# Joern 4.0.684. The archive is about 1.8 GB. pysrc2cpg and joern only need
# frontends/pysrc2cpg plus lib/, so the other language frontends are removed
# in this same layer.
ARG JOERN_VERSION=4.0.684
RUN curl -fL --retry 3 --retry-delay 2 -o /tmp/joern.zip \
        "https://github.com/joernio/joern/releases/download/v${JOERN_VERSION}/joern-cli-linux-x86_64.zip" \
    && unzip -q /tmp/joern.zip -d /opt \
    && rm /tmp/joern.zip \
    && find /opt/joern-cli/frontends -mindepth 1 -maxdepth 1 ! -name pysrc2cpg -exec rm -rf {} + \
    && test -x /opt/joern-cli/pysrc2cpg \
    && test -x /opt/joern-cli/joern \
    && test -d /opt/joern-cli/frontends/pysrc2cpg \
    && java -version

ENV JOERN_HOME=/opt/joern-cli
ENV PATH="/opt/joern-cli:${PATH}"

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
