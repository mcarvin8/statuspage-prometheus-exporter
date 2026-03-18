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
- [Run with Docker](#run-with-docker)

## Features

- **Status Monitoring**: Tracks operational status of services using Atlassian Status Page.io format
- **Incident Tracking**: Monitors active incidents with detailed metadata (ID, name, impact, affected components)
- **Maintenance Windows**: Tracks scheduled and active maintenance events
- **Response Time Metrics**: Records API response times for each status check
- **Prometheus Metrics**: Exposes standard Prometheus metrics on configurable port
- **Optional Slack alerts**: Incoming webhook posts when an incident opens or resolves (see below)

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

## Run with Docker

The usual way to run the exporter is the published image on [Docker Hub](https://hub.docker.com/r/mcarvin8/statuspage-prometheus-exporter): configure **`services.json`**, mount it into the container, then add **optional environment variables** as needed.

### 1. Create `services.json`

Define each status page you want to monitor. The image ships with `services.json.example` as a template.

```json
{
  "service_key": {
    "url": "https://status.example.com/api/v2/summary.json",
    "name": "Example Service"
  }
}
```

| Field | Description |
|-------|-------------|
| `url` | Full URL to the Statuspage API summary (typically `…/api/v2/summary.json`). |
| `name` | Label used in Prometheus metrics for this app. |

### 2. Run the container (minimum)

You **must** mount your `services.json` to the path below (or set `SERVICES_JSON_PATH` to match where you mount it). Metrics are served on **9001** by default.

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  mcarvin8/statuspage-prometheus-exporter:latest
```

### 3. Optional environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `METRICS_PORT` | `9001` | Port for the Prometheus metrics HTTP server. |
| `SERVICES_JSON_PATH` | `/app/statuspage-exporter/services.json` | Path to `services.json` *inside* the container (change if you mount elsewhere). |
| `CHECK_INTERVAL_MINUTES` | `20` | Minutes between status checks. |
| `DEBUG` | off | Set to `true` for debug logging. |
| `CLEAR_CACHE` | off | Set to `true` to delete cache files on startup. |
| `SLACK_WEBHOOK_URL` | _(unset)_ | Optional [Slack incoming webhook](https://api.slack.com/messaging/webhooks). When set, sends one message per **new** incident and per **resolved** incident (not one message per app). Posts are async; omit the variable to disable Slack. |

### 4. Example with common options

Combine flags as needed—for example, faster checks, debug logs, and Slack:

```bash
docker run -d \
  --name statuspage-exporter \
  -p 9001:9001 \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  -e CHECK_INTERVAL_MINUTES=10 \
  -e DEBUG=true \
  -e SLACK_WEBHOOK_URL='https://hooks.slack.com/services/T000/B000/XXXX' \
  mcarvin8/statuspage-prometheus-exporter:latest
```
