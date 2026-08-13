# Atlassian StatusPage.io Prometheus Exporter

![Docker Image Version (latest by date)](https://img.shields.io/docker/v/mcarvin8/statuspage-prometheus-exporter?sort=date)
![Docker Pulls](https://img.shields.io/docker/pulls/mcarvin8/statuspage-prometheus-exporter)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/mcarvin8/statuspage-prometheus-exporter)
![PyPI](https://img.shields.io/pypi/v/statuspage-prometheus-exporter)
![Coverage](https://raw.githubusercontent.com/mcarvin8/statuspage-prometheus-exporter/refs/heads/main/badges/coverage.svg)

Polls StatusPage.io summary APIs and exposes health, incidents, maintenance, and components as Prometheus metrics (and optional Slack alerts on incident open/resolve).

## Table of Contents

- [Features](#features)
- [Metrics](#metrics)
- [Caching](#caching)
- [Run with Docker](#run-with-docker)
- [Run as a Python Package (pip)](#run-as-a-python-package-pip)
- [One-Time Run Mode (Cron)](#one-time-run-mode-cron)
- [Kubernetes Example](#kubernetes-example)

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
| `statuspage_maintenance_info` | `service_name`, `maintenance_id`, … | `1` while maintenance is active or scheduled |
| `statuspage_component_status` | `service_name`, `component_name` | `1` operational component, `0` degraded/outage |
| `statuspage_component_timestamp` | `service_name`, `component_name` | Ms epoch; refreshed each successful poll |
| `statuspage_probe_check` | `service_name` | `1` if this run used a live response or cache fallback |
| `statuspage_application_timestamp` | `service_name` | Ms epoch; refreshed each successful poll |

## Caching

The exporter writes the last successful summary per service to disk. **If a request fails**, metrics can still be driven from that snapshot so Prometheus doesn’t clear and re-fire alerts on transient errors.

Gauges are **updated every check** so series stay “fresh” in Grafana. For **incidents and maintenance**, labels for an existing ID are kept aligned with the cached snapshot so the same time series continues; **new** IDs get labels from the API. Meaningful changes (status, incident/maintenance IDs, component status) trigger cache writes; response time is not cached.

If you run this container on Kubernetes (or any orchestrator that replaces pods/containers), mount `/app/statuspage-exporter/cache` to persistent storage (PVC/PV). Keeping cache files across restarts avoids re-notifying already-known active incidents as newly opened after redeploys.

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
| `RUN_MODE` | `daemon` | `daemon` runs continuously on a schedule; `once` runs a single pass and exits (see [One-Time Run Mode](#one-time-run-mode-cron)) |
| `METRICS_PORT` | `9001` | Metrics HTTP port (`daemon` mode only) |
| `SERVICES_JSON_PATH` | `/app/statuspage-exporter/services.json` | Path to config inside the container |
| `CHECK_INTERVAL_MINUTES` | `20` | Poll interval (`daemon` mode only) |
| `METRICS_TEXTFILE_PATH` | `metrics/statuspage.prom` | Output path for the Prometheus textfile (`RUN_MODE=once` only) |
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

## Run as a Python Package (pip)

Prefer running on bare metal/a VM instead of Docker? The exporter is also published to [PyPI](https://pypi.org/project/statuspage-prometheus-exporter/):

```bash
pip install statuspage-prometheus-exporter
```

Run it from a directory containing your `services.json` (the console script looks for `./services.json` by default, same as the Docker image looks in its `WORKDIR` — set `SERVICES_JSON_PATH` to point elsewhere):

```bash
statuspage-prometheus-exporter
```

This runs the same always-on daemon as the Docker image, using the same [environment variables](#3-optional-environment-variables) (`METRICS_PORT`, `CHECK_INTERVAL_MINUTES`, `DEBUG`, `CLEAR_CACHE`, `SLACK_WEBHOOK_URL`, etc.). The cache directory (`./cache`) is also created relative to the directory you run it from.

If no `services.json` is found and `SERVICES_JSON_PATH` isn't set, it falls back to the bundled `services.json.example` (a demo service) and logs a warning — useful for a first smoke-test, not for real monitoring.

## One-Time Run Mode (Cron)

If you'd rather trigger checks on your own schedule (e.g. host Cron, a Kubernetes `CronJob`) instead of running this as a long-lived daemon, set `RUN_MODE=once`. The exporter runs a single pass over all services, writes the results to a Prometheus **textfile**, then exits — no HTTP server is started, so `METRICS_PORT` and `CHECK_INTERVAL_MINUTES` don't apply.

The textfile is written in the [Prometheus text exposition format](https://github.com/prometheus/node_exporter#textfile-collector), for pickup by node_exporter's `--collector.textfile.directory` (or any tool that scrapes `.prom` files). Works with either distribution:

```bash
# Docker
docker run --rm \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  -v /path/to/textfile-collector:/app/statuspage-exporter/metrics \
  -e RUN_MODE=once \
  mcarvin8/statuspage-prometheus-exporter:latest

# pip install
cd /path/to/your/project  # contains services.json
RUN_MODE=once METRICS_TEXTFILE_PATH=/path/to/textfile-collector/statuspage.prom \
  statuspage-prometheus-exporter
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `RUN_MODE` | `daemon` | Set to `once` for a single pass |
| `METRICS_TEXTFILE_PATH` | `metrics/statuspage.prom` | Where the `.prom` file is written inside the container; point it at your mounted textfile-collector directory |

Mount the same cache directory as in the daemon example if you want cache-based fallback across runs. The container's `HEALTHCHECK` targets the metrics HTTP endpoint and doesn't apply in this mode — it's harmless since the process exits right after the run.

### Example crontab entry

```
*/20 * * * * docker run --rm \
  -v /path/to/your/services.json:/app/statuspage-exporter/services.json \
  -v /path/to/textfile-collector:/app/statuspage-exporter/metrics \
  -e RUN_MODE=once \
  mcarvin8/statuspage-prometheus-exporter:latest
```

## Kubernetes Example

If you run this in Kubernetes, keep two mounts:
- `/app/statuspage-exporter/cache` on a PVC so incident cache survives pod restarts
- `/app/statuspage-exporter/services.json` from a ConfigMap (or other config source)

Store `SLACK_WEBHOOK_URL` in a Secret, not inline YAML.

### 1. Deployment (trimmed)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: statuspage-exporter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: statuspage-exporter
  template:
    metadata:
      labels:
        app: statuspage-exporter
    spec:
      containers:
        - name: exporter
          image: mcarvin8/statuspage-prometheus-exporter:latest
          ports:
            - containerPort: 9001
              name: web
          env:
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: statuspage-exporter-secrets
                  key: slack_webhook_url
          volumeMounts:
            - name: cache
              mountPath: /app/statuspage-exporter/cache
            - name: config
              mountPath: /app/statuspage-exporter/services.json
              subPath: services.json
              readOnly: true
      volumes:
        - name: cache
          persistentVolumeClaim:
            claimName: statuspage-exporter-cache
        - name: config
          configMap:
            name: statuspage-exporter-config
```

### 2. PersistentVolumeClaim (trimmed)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: statuspage-exporter-cache
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 100Mi
```

### 3. ConfigMap for `services.json` (trimmed)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: statuspage-exporter-config
data:
  services.json: |
    {
      "conga": {
        "url": "https://status.conga.com/api/v2/summary.json",
        "name": "Conga"
      },
      "gong": {
        "url": "https://status.gong.io/api/v2/summary.json",
        "name": "Gong"
      }
    }
```

> Tip: keep `CLEAR_CACHE` unset (default) in normal production operation so cache continuity prevents duplicate "incident opened" notifications after redeploys.
