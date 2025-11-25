FROM ubuntu:latest

# Set working directory
WORKDIR /app/statuspage-exporter

# Copy application files (excluding services.json - users should mount their own)
COPY src/atlassian-statuspage-prom-exporter/*.py /app/statuspage-exporter/
COPY src/atlassian-statuspage-prom-exporter/services.json.example /app/statuspage-exporter/services.json.example

# Copy documentation and license
COPY README.md /app/statuspage-exporter/README.md
COPY LICENSE.md /app/statuspage-exporter/LICENSE.md
COPY version.txt /app/statuspage-exporter/version.txt

# Create cache directory (will be used if not mounted)
RUN mkdir -p /app/statuspage-exporter/cache

# Install Python and dependencies
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir prometheus_client requests apscheduler && \
    rm -rf /var/lib/apt/lists/*

# Set the environment variables to use the venv
ENV PATH="/opt/venv/bin:$PATH"

# Run the application
ENTRYPOINT ["python3", "status_monitoring.py"]
EXPOSE 9001
