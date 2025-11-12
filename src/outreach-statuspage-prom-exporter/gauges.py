"""
Prometheus Metrics Definitions Module - Outreach Monitoring

This module defines all Prometheus Gauge metrics for the Outreach status page
monitoring service. These gauges track the operational status and component
health of Outreach's services.

Metrics:
    - outreach_status_gauge: Overall service operational status
        Labels: service_name, service_type
        Values: 1 (operational), 0 (maintenance), -1 (incident/down)
        
    - outreach_response_time_gauge: Page load and render time
        Labels: service_name, service_type
        Values: Response time in seconds
    
    - outreach_component_status: Individual component status
        Labels: service_name, component_name
        Values: 1 (operational), 0 (maintenance), -1 (degraded/down)
    
    - outreach_incident_info: Info metric for active incident metadata
        Labels: service_name, service_type, incident_id, incident_name, 
                impact, shortlink, started_at, affected_components
        Values: Always 1 when incident is active
    
    - outreach_maintenance_info: Info metric for active maintenance events
        Labels: service_name, service_type, maintenance_id, maintenance_name,
                scheduled_start, scheduled_end, shortlink, affected_components
        Values: Always 1 when maintenance is active

The metrics are designed for use in Grafana dashboards with:
    - Status indicator panels
    - Alert rules for service degradation/outages
    - Response time trend graphs
    - Component-level status tables
    - Incident drill-down with direct links and metadata
"""
from prometheus_client import Gauge

# Service status gauge (1=operational, 0=maintenance, -1=incident/down)
outreach_status_gauge = Gauge(
    'outreach_service_status',
    'Status of Outreach service (1=operational, 0=maintenance, -1=incident/down)',
    ['service_name', 'service_type']
)

# Response time gauge
outreach_response_time_gauge = Gauge(
    'outreach_response_time_seconds',
    'Response time for Outreach status page (includes JavaScript rendering)',
    ['service_name', 'service_type']
)

# Component status gauge
outreach_component_status = Gauge(
    'outreach_component_status',
    'Status of individual Outreach components (1=operational, 0=maintenance, -1=degraded/down)',
    ['service_name', 'component_name']
)

# Gauge for incident metadata (allows clearing stale incidents)
outreach_incident_info = Gauge(
    'outreach_incident_info',
    'Active incident metadata with ID, name, impact, and link',
    ['service_name', 'service_type', 'incident_id', 'incident_name', 
     'impact', 'shortlink', 'started_at', 'affected_components']
)

# Gauge for maintenance metadata (allows clearing stale maintenance events)
outreach_maintenance_info = Gauge(
    'outreach_maintenance_info',
    'Active maintenance event metadata with ID, name, schedule, and link',
    ['service_name', 'service_type', 'maintenance_id', 'maintenance_name',
     'scheduled_start', 'scheduled_end', 'shortlink', 'affected_components']
)

