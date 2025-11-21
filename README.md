# Atlassian StatusPage.io Prometheus Exporter

![Docker Image Version (latest by date)](https://img.shields.io/docker/v/mcarvin8/statuspage-prometheus-exporter?sort=date)
![Docker Pulls](https://img.shields.io/docker/pulls/mcarvin8/statuspage-prometheus-exporter)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/mcarvin8/statuspage-prometheus-exporter)
![Build Status](https://github.com/mcarvin8/statuspage-prometheus-exporter/actions/workflows/docker-publish.yml/badge.svg)


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
- `SERVICES_JSON_PATH`: Custom path to `services.json` file (default: `/app/statuspage-exporter/services.json`)
- `CHECK_INTERVAL_MINUTES`: Interval in minutes between status checks (default: `20`)

## Docker Setup

### Using the Published Docker Image

The easiest way to use this exporter is with the published Docker image from [Docker Hub](https://hub.docker.com/repository/docker/mcarvin8/statuspage-prometheus-exporter):

**Important**: You must mount your own `services.json` file. The image includes a `services.json.example` file as a template, but you should create your own configuration file with the services you want to monitor.

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  -e CHECK_INTERVAL_MINUTES=20 \
  mcarvin8/statuspage-prometheus-exporter:latest
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

### Prometheus Alerting Rules

The exporter provides metrics that can be used to create Prometheus alerting rules for incidents, service status changes, and component degradation.

An example PrometheusRule manifest is provided in `prometheus/prometheusrule-example.yaml` that demonstrates:

- **Incident Alerts**: Alert when active incidents are detected for specific services
- **Service Status Alerts**: Alert on service status changes (down, maintenance)
- **Component Alerts**: Alert when individual components are degraded
- **Performance Alerts**: Alert on slow API response times
- **Generic Alerts**: Catch incidents across all monitored services

The example includes:
- Recording rules to aggregate incident metadata for easier alerting
- Alert rules with configurable thresholds and durations
- Template annotations with incident details (ID, name, impact, status page links)
- Customizable labels for routing to notification channels

To use the example:
1. Copy `prometheus/prometheusrule-example.yaml` to your Prometheus configuration
2. Update service names to match your `services.json` configuration
3. Customize alert thresholds, durations, and notification channels
4. Adjust metadata (namespace, labels) to match your Prometheus operator setup
5. Apply the manifest: `kubectl apply -f prometheus/prometheusrule-example.yaml`

## Monitoring Schedule

The exporter performs status checks:
- **Initial check**: Executes immediately on startup
- **Scheduled checks**: Configurable interval via `CHECK_INTERVAL_MINUTES` environment variable (default: 20 minutes)

You can customize the check interval by setting the `CHECK_INTERVAL_MINUTES` environment variable:

```bash
# Run checks every 10 minutes
export CHECK_INTERVAL_MINUTES=10

# Run checks every 30 minutes
export CHECK_INTERVAL_MINUTES=30
```

## Requirements

- Python 3.6+
- Dependencies:
  - `prometheus_client`
  - `requests`
  - `apscheduler`
