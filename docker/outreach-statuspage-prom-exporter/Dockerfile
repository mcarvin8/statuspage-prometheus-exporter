FROM ubuntu:latest

# Set working directory
WORKDIR /app/outreach

# Copy application files
COPY src/outreach-statuspage-prom-exporter /app/outreach

# Install Python, Chrome/Chromium, and dependencies
# Chrome/Chromium is required for Selenium to render JavaScript
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    curl \
    gnupg \
    unzip \
    && \
    # Install Google Chrome
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    # Create Python virtual environment
    python3 -m venv /opt/venv && \
    # Install Python dependencies from requirements.txt
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir \
        -r /app/outreach/requirements.txt && \
    # Clean up
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/*

# Set the environment variables to use the venv
ENV PATH="/opt/venv/bin:$PATH"

# Set Chrome/ChromeDriver environment variables for headless operation
ENV CHROME_BIN=/usr/bin/google-chrome \
    CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Run the application
ENTRYPOINT ["python3", "outreach_monitoring.py"]
EXPOSE 9001

