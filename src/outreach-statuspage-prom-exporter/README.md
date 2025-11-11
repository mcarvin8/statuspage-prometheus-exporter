# Outreach Monitoring Service

This service monitors the operational status of Outreach by parsing their HTML status page.

## Overview

Since Outreach doesn't expose a JSON API, this service uses Selenium to render the JavaScript-rendered React/MUI page and extracts:
- Overall service status
- Individual component statuses (Activity, Apps, Content, etc.)
- Active incidents and outages
- Scheduled maintenance events

## Dependencies

Install dependencies:
```bash
pip install -r requirements.txt
```

Key dependencies:
- `selenium` - For JavaScript rendering
- `webdriver-manager` - For automatic ChromeDriver management
- `beautifulsoup4` - For HTML parsing
- `prometheus-client` - For Prometheus metrics
- `apscheduler` - For scheduled monitoring

## Usage

Run the monitoring service:
```bash
python outreach_monitoring.py
```

The service will:
1. Start a Prometheus metrics server on port 9001 (configurable via `METRICS_PORT`)
2. Perform an initial status check
3. Schedule checks every 20 minutes

## Prometheus Metrics

The service exposes the following metrics:

- `outreach_service_status` - Overall service status (1=operational, 0=maintenance, -1=incident/down)
- `outreach_response_time_seconds` - Page load/render time
- `outreach_component_status` - Individual component statuses
- `outreach_incident_info` - Active incident metadata
- `outreach_maintenance_info` - Active maintenance metadata
- `outreach_check_failures_total` - Counter for failed checks

## Configuration

Environment Variables:
- `METRICS_PORT` - Prometheus metrics server port (default: 9001)

## Testing

To test the Outreach status checker independently:
```bash
python -c "from outreach_checker import check_outreach_status; import json; print(json.dumps(check_outreach_status(), indent=2))"
```

## Notes

- Requires Chrome/Chromium and ChromeDriver for JavaScript rendering
- ChromeDriver is automatically managed via `webdriver-manager` if available
- Falls back to static HTML parsing if Selenium is unavailable (may miss JavaScript-rendered content)

