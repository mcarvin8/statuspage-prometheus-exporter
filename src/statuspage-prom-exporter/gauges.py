"""
Prometheus Metrics Definitions Module - Atlassian Status Page Exporter

This module defines all Prometheus Gauge metrics for the Atlassian Status Page
Prometheus exporter. These gauges track the operational status and performance
of services monitored via Atlassian Status Page.io.

Metrics:
    - statuspage_status_gauge: Service operational status
        Labels: service_name, service_type
        Values: 1 (operational), 0 (maintenance), -1 (incident/down)
        
    - statuspage_response_time_gauge: API response time
        Labels: service_name, service_type
        Values: Response time in seconds
    
    - statuspage_check_failures_counter: Counter for failed status checks
        Labels: service_name, service_type, error_type
        Tracks: Request failures, JSON errors, and other check failures
    
    - statuspage_incident_info: Info metric for active incident metadata
        Labels: service_name, service_type, incident_id, incident_name, 
                impact, shortlink, started_at, affected_components
        Values: Always 1 when incident is active
    
    - statuspage_maintenance_info: Info metric for active maintenance events
        Labels: service_name, service_type, maintenance_id, maintenance_name,
                scheduled_start, scheduled_end, shortlink, affected_components
        Values: Always 1 when maintenance is active

The metrics are designed for use in Grafana dashboards with:
    - Status indicator panels
    - Alert rules for service degradation/outages
    - Response time trend graphs
    - Detailed status tables showing current state and details
    - Failure rate tracking and alerting
    - Incident drill-down with direct links and metadata
"""
from prometheus_client import Gauge, Counter

# Service status gauge (1=operational, 0=maintenance, -1=incident/down)
# Simplified to just track status value - incident details are in statuspage_incident_info
statuspage_status_gauge = Gauge(
    'statuspage_service_status',
    'Status of monitored services (1=operational, 0=maintenance, -1=incident/down)',
    ['service_name', 'service_type']
)

# Response time gauge
statuspage_response_time_gauge = Gauge(
    'statuspage_response_time_seconds',
    'Response time for status page API endpoints',
    ['service_name', 'service_type']
)

# Counter for tracking failed status checks
statuspage_check_failures_counter = Counter(
    'statuspage_check_failures_total',
    'Total number of failed status checks (request failures, timeouts, parse errors)',
    ['service_name', 'service_type', 'error_type']
)

# Gauge for incident metadata (allows clearing stale incidents)
statuspage_incident_info = Gauge(
    'statuspage_incident_info',
    'Active incident metadata with ID, name, impact, and link',
    ['service_name', 'service_type', 'incident_id', 'incident_name', 
     'impact', 'shortlink', 'started_at', 'affected_components']
)

# Gauge for maintenance metadata (allows clearing stale maintenance events)
statuspage_maintenance_info = Gauge(
    'statuspage_maintenance_info',
    'Active maintenance event metadata with ID, name, schedule, and link',
    ['service_name', 'service_type', 'maintenance_id', 'maintenance_name',
     'scheduled_start', 'scheduled_end', 'shortlink', 'affected_components']
)
