FROM ubuntu:latest

# Set working directory
WORKDIR /app/statuspage-exporter

# Copy application files
COPY . /app/statuspage-exporter

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
