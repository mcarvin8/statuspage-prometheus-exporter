FROM python:3.11-slim

# Set working directory
WORKDIR /app/statuspage-exporter

# Copy application files (excluding services.json - users should mount their own)
COPY src/*.py /app/statuspage-exporter/
COPY src/services.json.example /app/statuspage-exporter/services.json.example

# Copy documentation and license
COPY README.md /app/statuspage-exporter/README.md
COPY LICENSE.md /app/statuspage-exporter/LICENSE.md
COPY version.txt /app/statuspage-exporter/version.txt

LABEL org.opencontainers.image.title="statuspage-prometheus-exporter" \
      org.opencontainers.image.description="Prometheus exporter for Atlassian Statuspage monitoring" \
      org.opencontainers.image.authors="Matt Carvin <matthewjcarvin@gmail.com>" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/mcarvin8/statuspage-prometheus-exporter"

# Install dependencies and timezone data, create cache directory
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir prometheus_client requests apscheduler && \
    mkdir -p /app/statuspage-exporter/cache /app/statuspage-exporter/metrics

# Set the default timezone
ENV TZ=UTC

# Create non-root user for running the application (numeric UID for Kubernetes runAsNonRoot)
ARG EXPORTER_UID=1001
RUN useradd --uid ${EXPORTER_UID} --create-home --shell /bin/bash exporter && \
    chown -R exporter:exporter /app/statuspage-exporter

# Use numeric UID so Kubernetes can verify non-root when runAsNonRoot is set
USER ${EXPORTER_UID}

# Run the application
ENTRYPOINT ["python3", "status_monitoring.py"]
EXPOSE 9001

# Health check: verify metrics endpoint responds (uses METRICS_PORT env, default 9001)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import os, urllib.request; port = os.environ.get('METRICS_PORT', '9001'); urllib.request.urlopen(f'http://localhost:{port}/metrics')" || exit 1
