"""
Prometheus Metrics Definitions Module - Atlassian Status Page Exporter

This module defines all Prometheus Gauge metrics for the Atlassian Status Page
Prometheus exporter. These gauges track the operational status and performance
of services monitored via Atlassian Status Page.io.

Metrics:
    - statuspage_status_gauge: Service operational status
        Labels: service_name
        Values: 1 (operational), 0 (incident/down)
        
    - statuspage_response_time_gauge: API response time
        Labels: service_name
        Values: Response time in seconds

    - statuspage_incident_info: Info metric for active incident metadata
        Labels: service_name, incident_id, incident_name, 
                impact, shortlink, started_at, affected_components
        Values: Always 1 when incident is active
    
    - statuspage_maintenance_info: Info metric for active maintenance events
        Labels: service_name, maintenance_id, maintenance_name,
                scheduled_start, scheduled_end, shortlink, affected_components
        Values: Always 1 when maintenance is active

    - statuspage_component_status: Individual component status
        Labels: service_name, component_name
        Values: 1 (operational), 0 (degraded/down/unknown)
    
    - statuspage_component_timestamp: Last update timestamp of component
        Labels: service_name, component_name
        Values: Unix timestamp in milliseconds
    
    - statuspage_probe_check: Whether all queries on the application were successful
        Labels: service_name
        Values: 1 (all successful), 0 (at least one failed)
    
    - statuspage_application_timestamp: Timestamp of last update of overall application status
        Labels: service_name
        Values: Unix timestamp in milliseconds

The metrics are designed for use in Grafana dashboards with:
    - Status indicator panels
    - Alert rules for service degradation/outages
    - Response time trend graphs
    - Detailed status tables showing current state and details
    - Incident drill-down with direct links and metadata
"""
from prometheus_client import Gauge

# Service status gauge (1=operational, 0=incident/down)
# Simplified to just track status value - incident details are in statuspage_incident_info
statuspage_status_gauge = Gauge(
    'statuspage_service_status',
    'Status of monitored services (1=operational, 0=incident/down)',
    ['service_name']
)

# Response time gauge
statuspage_response_time_gauge = Gauge(
    'statuspage_response_time_seconds',
    'Response time for status page API endpoints',
    ['service_name']
)

# Gauge for incident metadata (allows clearing stale incidents)
statuspage_incident_info = Gauge(
    'statuspage_incident_info',
    'Active incident metadata with ID, name, impact, and link',
    ['service_name', 'incident_id', 'incident_name', 
     'impact', 'shortlink', 'started_at', 'affected_components']
)

# Gauge for maintenance metadata (allows clearing stale maintenance events)
statuspage_maintenance_info = Gauge(
    'statuspage_maintenance_info',
    'Active maintenance event metadata with ID, name, schedule, and link',
    ['service_name', 'maintenance_id', 'maintenance_name',
     'scheduled_start', 'scheduled_end', 'shortlink', 'affected_components']
)

# Component status gauge
statuspage_component_status = Gauge(
    'statuspage_component_status',
    'Status of individual service components (1=operational, 0=degraded/down/unknown)',
    ['service_name', 'component_name']
)

# Component timestamp gauge
statuspage_component_timestamp = Gauge(
    'statuspage_component_timestamp',
    'Last update timestamp of component in Unix epoch milliseconds',
    ['service_name', 'component_name']
)

# Probe check gauge
statuspage_probe_check = Gauge(
    'statuspage_probe_check',
    'Whether all queries on the application were successful (1=all successful, 0=at least one failed)',
    ['service_name']
)

# Application timestamp gauge
statuspage_application_timestamp = Gauge(
    'statuspage_application_timestamp',
    'Timestamp of last update of overall application status in Unix epoch milliseconds',
    ['service_name']
)
