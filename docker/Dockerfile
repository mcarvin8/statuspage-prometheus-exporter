FROM ubuntu:latest

# Set working directory
WORKDIR /app/statuspage-exporter

# Copy application files (excluding services.json - users should mount their own)
COPY src/*.py /app/statuspage-exporter/
COPY src/services.json.example /app/statuspage-exporter/services.json.example

# Copy documentation and license
COPY README.md /app/statuspage-exporter/README.md
COPY LICENSE.md /app/statuspage-exporter/LICENSE.md
COPY version.txt /app/statuspage-exporter/version.txt

# Install Python and dependencies, create cache directory
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir prometheus_client requests apscheduler && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /app/statuspage-exporter/cache

# Set the environment variables to use the venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for running the application
RUN useradd --create-home --shell /bin/bash exporter && \
    chown -R exporter:exporter /app/statuspage-exporter /opt/venv

USER exporter

# Run the application
ENTRYPOINT ["python3", "status_monitoring.py"]
EXPOSE 9001
