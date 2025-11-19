# Atlassian StatusPage.io Prometheus Exporter

A Prometheus exporter that monitors services using Atlassian StatusPage.io status pages. This exporter periodically checks status page APIs to track service health, incidents, and maintenance windows, exposing metrics for integration with Prometheus and Grafana.

## Features

- **Status Monitoring**: Tracks operational status of services using Atlassian Status Page.io format
- **Incident Tracking**: Monitors active incidents with detailed metadata (ID, name, impact, affected components)
- **Maintenance Windows**: Tracks scheduled and active maintenance events
- **Response Time Metrics**: Records API response times for each status check
- **Prometheus Metrics**: Exposes standard Prometheus metrics on configurable port

## Metrics Exposed

The exporter exposes the following Prometheus metrics:

- `statuspage_service_status`: Service operational status (1=operational, 0=maintenance, -1=incident/down)
  - Labels: `service_name`
  
- `statuspage_response_time_seconds`: API response time in seconds
  - Labels: `service_name`
  
- `statuspage_incident_info`: Active incident metadata
  - Labels: `service_name`, `incident_id`, `incident_name`, `impact`, `shortlink`, `started_at`, `affected_components`
  
- `statuspage_maintenance_info`: Active maintenance event metadata
  - Labels: `service_name`, `maintenance_id`, `maintenance_name`, `scheduled_start`, `scheduled_end`, `shortlink`, `affected_components`

- `statuspage_component_status`: Individual component status
  - Labels: `service_name`, `component_name`

## Metric Caching Strategy

The exporter uses intelligent caching to minimize unnecessary Prometheus gauge updates and prevent alert churn. This ensures that gauges are only cleared and reset when there are actual changes to the monitored data.

### Cached Metrics (Update Only on Change)

The following metrics use cache comparison to avoid unnecessary updates:

- **`statuspage_service_status`**: Only updates when the service status changes (operational/maintenance/incident transitions)
- **`statuspage_incident_info`**: Only updates when incidents are added, removed, or their IDs change
- **`statuspage_maintenance_info`**: Only updates when maintenance events are added, removed, or their IDs change
- **`statuspage_component_status`**: Only updates when components are added, removed, or their status values change

**How it works:**
1. Before each status check, the exporter loads the previous cached state for each service
2. After collecting current status data, it compares the current state with the cached state
3. Gauges are only updated when differences are detected (new items, removed items, or status changes)
4. If no cache exists (first run or cache cleared), all gauges update normally to establish the initial state
5. Resolved incidents and completed maintenance events are cleared by setting their gauge values to 0 using cached metadata to match exact labels

**Benefits:**
- Prevents unnecessary Prometheus gauge writes on every check cycle
- Reduces alert churn by avoiding gauge resets when data hasn't changed
- Maintains metric continuity even when individual API requests fail (falls back to cached data)
- Ensures accurate metrics by always updating on actual state changes

### Non-Cached Metric (Always Updates)

- **`statuspage_response_time_seconds`**: Always cleared and updated every run
  - Response times are dynamic metrics used for performance trending
  - This metric is not used for alerts, so frequent updates are acceptable
  - Provides continuous tracking of API performance over time

## Configuration

### Service Configuration

Configure the services you want to monitor in `services.json`:

```json
{
  "service_key": {
    "url": "https://status.example.com/api/v2/summary.json",
    "name": "Example Service"
  }
}
```

Each service requires:
- `url`: The full URL to the Status Page.io API summary endpoint (typically `/api/v2/summary.json`)
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

You can modify the schedule by editing the cron trigger in `status_monitoring.py`:

```python
CronTrigger(minute='*/20')  # Change to your desired interval
```

## Requirements

- Python 3.6+
- Dependencies:
  - `prometheus_client`
  - `requests`
  - `apscheduler`
