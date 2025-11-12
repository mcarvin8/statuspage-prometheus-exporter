# Atlassian Status Page Prometheus Exporter

A Prometheus exporter that monitors services using Atlassian Status Page.io status pages. This exporter periodically checks status page APIs to track service health, incidents, and maintenance windows, exposing metrics for integration with Prometheus and Grafana.

## Features

- **Status Monitoring**: Tracks operational status of services using Atlassian Status Page.io format
- **Incident Tracking**: Monitors active incidents with detailed metadata (ID, name, impact, affected components)
- **Maintenance Windows**: Tracks scheduled and active maintenance events
- **Response Time Metrics**: Records API response times for each status check
- **Failure Tracking**: Counts failed status checks for operational visibility
- **Prometheus Metrics**: Exposes standard Prometheus metrics on configurable port

## Metrics Exposed

The exporter exposes the following Prometheus metrics:

- `statuspage_service_status`: Service operational status (1=operational, 0=maintenance, -1=incident/down)
  - Labels: `service_name`, `service_type`
  
- `statuspage_response_time_seconds`: API response time in seconds
  - Labels: `service_name`, `service_type`
  
- `statuspage_incident_info`: Active incident metadata
  - Labels: `service_name`, `service_type`, `incident_id`, `incident_name`, `impact`, `shortlink`, `started_at`, `affected_components`
  
- `statuspage_maintenance_info`: Active maintenance event metadata
  - Labels: `service_name`, `service_type`, `maintenance_id`, `maintenance_name`, `scheduled_start`, `scheduled_end`, `shortlink`, `affected_components`

- `statuspage_component_status`: Individual component status
  - Labels: `service_name`, `component_name`

## Configuration

### Service Configuration

Configure the services you want to monitor in `services.json`:

```json
{
  "service_key": {
    "url": "https://status.example.com/api/v2/summary.json",
    "type": "status_page",
    "name": "Example Service"
  }
}
```

Each service requires:
- `url`: The full URL to the Status Page.io API summary endpoint (typically `/api/v2/summary.json`)
- `type`: Currently supports `"status_page"` for Atlassian Status Page.io format
- `name`: Display name for the service in metrics

### Environment Variables

- `METRICS_PORT`: Port for Prometheus metrics server (default: `9001`)

## Docker Setup

### Building the Docker Image

Build the Docker image from the project root:

```bash
docker build -t statuspage-prometheus-exporter -f docker/Dockerfile .
```

### Running with Docker

Run the container with your `services.json` configuration:

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/services.json:/app/statuspage-exporter/services.json \
  statuspage-prometheus-exporter
```

Or using Docker Compose:

```yaml
version: '3.8'
services:
  statuspage-exporter:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "9001:9001"
    volumes:
      - ./services.json:/app/statuspage-exporter/services.json
    environment:
      - METRICS_PORT=9001
    restart: unless-stopped
```

### Docker Compose Example

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'
services:
  statuspage-exporter:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "9001:9001"
    volumes:
      - ./services.json:/app/statuspage-exporter/services.json
    environment:
      - METRICS_PORT=9001
    restart: unless-stopped
```

2. Start the service:

```bash
docker-compose up -d
```

## Integration with Prometheus

Add the exporter to your Prometheus configuration (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'statuspage-exporter'
    scrape_interval: 30s
    static_configs:
      - targets: ['statuspage-exporter:9001']
```

## Monitoring Schedule

The exporter performs status checks:
- **Initial check**: Executes immediately on startup
- **Scheduled checks**: Every 20 minutes via APScheduler

You can modify the schedule by editing the cron trigger in `bizapps_monitoring.py`:

```python
CronTrigger(minute='*/20')  # Change to your desired interval
```

## Example Queries

### Check service status

```promql
statuspage_service_status
```

### Find services with active incidents

```promql
statuspage_service_status == -1
```

### Get incident details

```promql
statuspage_incident_info
```

### Track response times

```promql
statuspage_response_time_seconds
```

### Monitor check failures

```promql
rate(statuspage_check_failures_total[5m])
```

## Requirements

- Python 3.6+
- Dependencies:
  - `prometheus_client`
  - `requests`
  - `apscheduler

