# Atlassian StatusPage.io Prometheus Exporter

![Docker Image Version (latest by date)](https://img.shields.io/docker/v/mcarvin8/statuspage-prometheus-exporter?sort=date)
![Docker Pulls](https://img.shields.io/docker/pulls/mcarvin8/statuspage-prometheus-exporter)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/mcarvin8/statuspage-prometheus-exporter)

Polls StatusPage.io summary APIs and exposes health, incidents, maintenance, and components as Prometheus metrics (and optional Slack alerts on incident open/resolve).

## Table of Contents

- [Features](#features)
- [Metrics](#metrics)
- [Caching](#caching)
- [Run with Docker](#run-with-docker)

## Features

- Service + component status, incidents, scheduled maintenance  
- Per-check API latency; probe success flag  
- On-disk cache when the API fails (fewer flaky alerts)  
- Optional **Slack** webhook: one post per incident opened / resolved  

## Metrics

| Metric | Labels | Meaning |
|--------|--------|---------|
| `statuspage_service_status` | `service_name` | `1` operational, `0` incident/degraded |
| `statuspage_response_time_seconds` | `service_name` | Summary API request duration |
| `statuspage_incident_info` | `service_name`, `incident_id`, `incident_name`, `impact`, `shortlink`, `started_at`, `affected_components` | `1` while incident active |
| `statuspage_maintenance_info` | `service_name`, `maintenance_id`, … | `1` while maintenance active |
| `statuspage_component_status` | `service_name`, `component_name` | `1` operational component, `0` degraded/outage |
| `statuspage_component_timestamp` | `service_name`, `component_name` | Ms epoch; refreshed each successful poll |
| `statuspage_probe_check` | `service_name` | `1` if this run used a live response or cache fallback |
| `statuspage_application_timestamp` | `service_name` | Ms epoch; refreshed each successful poll |

## Caching

The exporter writes the last successful summary per service to disk. **If a request fails**, metrics can still be driven from that snapshot so Prometheus doesn’t clear and re-fire alerts on transient errors.

Gauges are **updated every check** so series stay “fresh” in Grafana. For **incidents and maintenance**, labels for an existing ID are kept aligned with the cached snapshot so the same time series continues; **new** IDs get labels from the API. Meaningful changes (status, incident/maintenance IDs, component status) trigger cache writes; response time is not cached.

## Run with Docker

Use the image from [Docker Hub](https://hub.docker.com/r/mcarvin8/statuspage-prometheus-exporter): add **`services.json`**, mount it, then set **env vars** if you need non-defaults.

### 1. Create `services.json`

The image includes `services.json.example` as a template.

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
| `url` | Summary endpoint, usually `…/api/v2/summary.json` |
| `name` | `service_name` label in metrics |

### 2. Run the container (minimum)

Mount `services.json` to the path below, or set `SERVICES_JSON_PATH` to match your mount. Metrics listen on **9001** unless you change `METRICS_PORT`.

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
| `METRICS_PORT` | `9001` | Metrics HTTP port |
| `SERVICES_JSON_PATH` | `/app/statuspage-exporter/services.json` | Path to config inside the container |
| `CHECK_INTERVAL_MINUTES` | `20` | Poll interval |
| `DEBUG` | off | `true` → debug logs |
| `CLEAR_CACHE` | off | `true` → wipe cache on startup |
| `SLACK_WEBHOOK_URL` | _(unset)_ | [Slack webhook](https://api.slack.com/messaging/webhooks): one message per new / resolved incident |

### 4. Example with common options

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
