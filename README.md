# Atlassian StatusPage.io Prometheus Exporter

![Docker Image Version (latest by date)](https://img.shields.io/docker/v/mcarvin8/statuspage-prometheus-exporter?sort=date)
![Docker Pulls](https://img.shields.io/docker/pulls/mcarvin8/statuspage-prometheus-exporter)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/mcarvin8/statuspage-prometheus-exporter)

A Prometheus exporter that monitors services using Atlassian StatusPage.io status pages. This exporter periodically checks status page APIs to track service health, incidents, and maintenance windows, exposing metrics for integration with Prometheus and Grafana.

## Table of Contents

- [Features](#features)
- [Metrics Exposed](#metrics-exposed)
- [Metric Caching Strategy](#metric-caching-strategy)
  - [Cached Metrics (Update Only on Change)](#cached-metrics-update-only-on-change)
  - [Non-Cached Metric (Always Updates)](#non-cached-metric-always-updates)
- [Configuration](#configuration)
  - [Service Configuration](#service-configuration)
  - [Environment Variables](#environment-variables)
- [Docker Setup](#docker-setup)
  - [Using the Published Docker Image](#using-the-published-docker-image)
- [Integration with Prometheus](#integration-with-prometheus)
  - [Prometheus Alerting Rules](#prometheus-alerting-rules)
- [Monitoring Schedule](#monitoring-schedule)
- [Requirements](#requirements)

## Features

- **Status Monitoring**: Tracks operational status of services using Atlassian Status Page.io format
- **Incident Tracking**: Monitors active incidents with detailed metadata (ID, name, impact, affected components)
- **Maintenance Windows**: Tracks scheduled and active maintenance events
- **Response Time Metrics**: Records API response times for each status check
- **Prometheus Metrics**: Exposes standard Prometheus metrics on configurable port

## Metrics Exposed

The exporter exposes the following Prometheus metrics:

- `statuspage_service_status`: Service operational status (1=operational, 0=incident/down)
  - Labels: `service_name`
  
- `statuspage_response_time_seconds`: API response time in seconds
  - Labels: `service_name`
  
- `statuspage_incident_info`: Active incident metadata
  - Labels: `service_name`, `incident_id`, `incident_name`, `impact`, `shortlink`, `started_at`, `affected_components`
  
- `statuspage_maintenance_info`: Active maintenance event metadata
  - Labels: `service_name`, `maintenance_id`, `maintenance_name`, `scheduled_start`, `scheduled_end`, `shortlink`, `affected_components`

- `statuspage_component_status`: Individual component status
  - Labels: `service_name`, `component_name`
  
- `statuspage_component_timestamp`: Last update timestamp of component
  - Labels: `service_name`, `component_name`
  - Values: Unix timestamp in milliseconds (for better Grafana compatibility)
  
- `statuspage_probe_check`: Whether all queries on the application were successful
  - Labels: `service_name`
  - Values: 1 (all successful), 0 (at least one failed)
  
- `statuspage_application_timestamp`: Timestamp of last update of overall application status
  - Labels: `service_name`
  - Values: Unix timestamp in milliseconds (for better Grafana compatibility)

## Metric Caching Strategy

The exporter uses intelligent caching to maintain metric freshness in Prometheus while preventing duplicate alerts. Gauges are always updated to keep metrics fresh, while the cache is used to preserve labels for existing incidents/maintenance to prevent alert churn.

### Gauge Update Strategy (Always Fresh)

All metrics are updated on every check cycle to ensure Prometheus knows they're still active and they appear correctly in Grafana dashboards:

- **`statuspage_service_status`**: Always updated (even if status unchanged) to keep metrics fresh
- **`statuspage_incident_info`**: Always updated for active incidents to maintain freshness
- **`statuspage_maintenance_info`**: Always updated for active maintenance to maintain freshness
- **`statuspage_component_status`**: Always updated for all components to maintain freshness
- **`statuspage_component_timestamp`**: Always updated with current timestamp
- **`statuspage_application_timestamp`**: Always updated with current timestamp
- **`statuspage_response_time_seconds`**: Always cleared and updated every run (dynamic metric)
- **`statuspage_probe_check`**: Always updated to reflect current probe status

**Label Preservation for Duplicate Alert Prevention:**
- For existing incidents/maintenance (same ID), labels are preserved from cache to prevent duplicate alerts
- For new incidents/maintenance, current labels from the API are used
- This ensures Prometheus recognizes them as the same metric series, preventing alert re-firing

### Cache Management Strategy

The cache is used for two purposes:
1. **Fallback on API failures**: If an API request fails, cached data is used to maintain metric continuity
2. **Label preservation**: Existing incident/maintenance labels are preserved to prevent duplicate alerts

**Cache Update Logic:**
- Cache only updates when meaningful values change (status, incident IDs, maintenance IDs, component status)
- `response_time` is excluded from cache (not used for alerts)
- Labels for existing incidents/maintenance are preserved from cache to maintain consistent metric series
- Cache comparison is used for logging changes, but doesn't prevent gauge updates

**Benefits:**
- Metrics stay fresh in Prometheus and Grafana dashboards
- Prevents duplicate alerts by preserving labels for existing incidents/maintenance
- Maintains metric continuity even when individual API requests fail (falls back to cached data)
- Reduces unnecessary cache writes by only updating when meaningful data changes

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
- `DEBUG`: Enable debug logging (set to `true` to enable, default: `false`/INFO level)
- `CLEAR_CACHE`: Clear all cache files on startup (set to `true` to enable, default: `false`)

## Docker Setup

### Using the Published Docker Image

The easiest way to use this exporter is with the published Docker image from [Docker Hub](https://hub.docker.com/repository/docker/mcarvin8/statuspage-prometheus-exporter):

**Required**: You **must** mount your own `services.json` file for the exporter to work. The image includes a `services.json.example` file as a template, but you must create your own configuration file with the services you want to monitor.

**Optional**: Environment variables can be set to customize behavior. See the [Environment Variables](#environment-variables) section above for available options and their defaults.

#### Minimal Required Setup

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  mcarvin8/statuspage-prometheus-exporter:latest
```

#### With Optional Environment Variables

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  -e CHECK_INTERVAL_MINUTES=20 \
  -e DEBUG=true \
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
