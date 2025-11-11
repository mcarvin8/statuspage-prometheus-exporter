"""
Outreach Monitoring Orchestration Module

This module orchestrates the monitoring of Outreach by checking their status page,
parsing the HTML, and updating Prometheus metrics with the results.

Functions:
    - monitor_outreach: Main orchestration function that checks Outreach status
      and updates Prometheus gauges

Process Flow:
    1. Check Outreach status page and collect status check results
    2. Clear existing Prometheus gauge labels to prevent stale metrics
    3. Immediately update all Prometheus metrics with collected results
    4. Track failed checks in a separate counter metric
    
    This approach minimizes the window where Prometheus might scrape empty gauges
    by collecting all data before clearing and updating gauges atomically.

Metrics Updated:
    - outreach_status_gauge: Service health status (-1=incident, 0=maintenance, 1=operational)
    - outreach_response_time_gauge: Page load/render time in seconds
    - outreach_component_status: Individual component statuses
    - outreach_incident_info: Active incident metadata (ID, name, impact, shortlink, etc.)
    - outreach_maintenance_info: Active maintenance metadata (ID, name, schedule, shortlink, etc.)
    - outreach_check_failures_counter: Counter for failed status checks

The orchestration ensures consistent metric labels and handles both successful
and failed status checks gracefully. Failed checks are logged and counted but
do not trigger incident alerts.
"""
import logging
import re
from outreach_checker import check_outreach_status
from gauges import (outreach_status_gauge, outreach_response_time_gauge, 
                    outreach_check_failures_counter, outreach_incident_info,
                    outreach_maintenance_info, outreach_component_status)

logger = logging.getLogger(__name__)

SERVICE_NAME = "Outreach"
SERVICE_TYPE = "html_status_page"

def normalize_timestamp(timestamp_str):
    """
    Normalize ISO 8601 timestamp to seconds precision (remove milliseconds).
    This prevents duplicate gauge entries due to timestamp precision differences.
    
    Args:
        timestamp_str: ISO 8601 timestamp string (e.g., '2025-11-04T13:25:38.181Z')
        
    Returns:
        Normalized timestamp string with seconds precision (e.g., '2025-11-04T13:25:38Z')
    """
    if not timestamp_str or timestamp_str == 'N/A' or timestamp_str == 'unknown':
        return timestamp_str
    
    # Remove milliseconds by replacing .XXX pattern before Z or timezone offset
    normalized = re.sub(r'\.\d{3}(?=[Z\+\-])', '', timestamp_str)
    return normalized

def monitor_outreach():
    """
    Monitor Outreach status page and update Prometheus metrics.
    
    Process Flow:
    1. Check Outreach status page
    2. Clear existing Prometheus gauge labels to remove stale metrics
    3. Immediately update all gauges with collected results
    
    This minimizes the window where Prometheus might scrape empty gauges
    by collecting all data before clearing and updating.
    """
    logger.info("Starting Outreach monitoring...")
    
    # Step 1: Check Outreach status
    result = check_outreach_status()
    
    # Log result immediately
    if result['success']:
        logger.info(f"Outreach: {result['raw_status']} "
                   f"(response time: {result['response_time']:.2f}s)")
    else:
        logger.warning(f"Outreach: Check failed ({result.get('raw_status', 'unknown')}), skipping gauge update - {result.get('error', 'Unknown error')}")
    
    # Step 2: Clear all existing gauge labels to remove stale metrics
    logger.debug("Clearing existing gauge labels before updating with new data...")
    outreach_status_gauge.clear()
    outreach_response_time_gauge.clear()
    outreach_component_status.clear()
    outreach_incident_info.clear()
    outreach_maintenance_info.clear()
    
    # Step 3: Update all gauges with collected results
    status_value = result.get('status')
    status_text = result.get('status_text', 'Unknown')
    details = result.get('details', 'No details available')
    
    logger.debug(f"Updating gauge for {SERVICE_NAME}: status={status_value} ({status_text}), details='{details}'")
    
    # Only update gauges if status check succeeded or returned a valid status
    if status_value is not None:
        # Update main status gauge
        outreach_status_gauge.labels(
            service_name=SERVICE_NAME,
            service_type=SERVICE_TYPE
        ).set(status_value)
        
        outreach_response_time_gauge.labels(
            service_name=SERVICE_NAME,
            service_type=SERVICE_TYPE
        ).set(result['response_time'])
        
        # Update component status gauges
        components = result.get('components', [])
        if components:
            logger.debug(f"{SERVICE_NAME}: Processing {len(components)} component(s) for component_status gauge")
            for comp in components:
                comp_name = comp.get('name', 'Unknown')
                comp_status = comp.get('status', 'unknown')
                
                # Map status to numeric value
                status_mapping = {
                    'operational': 1,
                    'maintenance': 0,
                    'degraded': -1,
                    'down': -1,
                    'unknown': 1  # Default to operational
                }
                comp_status_value = status_mapping.get(comp_status.lower(), 1)
                
                outreach_component_status.labels(
                    service_name=SERVICE_NAME,
                    component_name=comp_name
                ).set(comp_status_value)
                
                logger.debug(f"{SERVICE_NAME}: Component {comp_name} - {comp_status} ({comp_status_value})")
            
            logger.info(f"{SERVICE_NAME}: {len(components)} component(s) tracked in component_status gauge")
        
        # Update incident metadata gauge for each active incident
        incident_metadata = result.get('incident_metadata', [])
        if incident_metadata:
            logger.debug(f"{SERVICE_NAME}: Processing {len(incident_metadata)} incident(s) for incident_info gauge")
            for idx, incident in enumerate(incident_metadata):
                # Truncate fields to avoid excessive cardinality
                incident_name = incident.get('name', 'Unknown')[:100]
                affected = ', '.join(incident.get('affected_components', []))[:150]
                incident_id = incident.get('id', 'unknown')
                impact = incident.get('impact', 'unknown')
                shortlink = incident.get('shortlink', 'N/A')
                started_at = normalize_timestamp(incident.get('started_at', 'unknown'))
                
                logger.debug(f"{SERVICE_NAME}: Incident #{idx+1} details:")
                logger.debug(f"  - ID: {incident_id}")
                logger.debug(f"  - Name: {incident_name}")
                logger.debug(f"  - Impact: {impact}")
                logger.debug(f"  - Shortlink: {shortlink}")
                logger.debug(f"  - Started: {started_at}")
                logger.debug(f"  - Affected: {affected}")
                
                outreach_incident_info.labels(
                    service_name=SERVICE_NAME,
                    service_type=SERVICE_TYPE,
                    incident_id=incident_id,
                    incident_name=incident_name,
                    impact=impact,
                    shortlink=shortlink,
                    started_at=started_at,
                    affected_components=affected
                ).set(1)
                
                logger.debug(f"{SERVICE_NAME}: Set outreach_incident_info gauge to 1 for incident {incident_id}")
                
            logger.info(f"{SERVICE_NAME}: {len(incident_metadata)} active incident(s) tracked in incident_info gauge")
        else:
            # Set gauge to 0 when there are no incidents to always show service status
            logger.debug(f"{SERVICE_NAME}: No incident metadata - setting outreach_incident_info gauge to 0")
            outreach_incident_info.labels(
                service_name=SERVICE_NAME,
                service_type=SERVICE_TYPE,
                incident_id='none',
                incident_name='No Active Incidents',
                impact='none',
                shortlink='N/A',
                started_at='N/A',
                affected_components='N/A'
            ).set(0)
        
        # Update maintenance metadata gauge for each active maintenance
        maintenance_metadata = result.get('maintenance_metadata', [])
        if maintenance_metadata:
            logger.debug(f"{SERVICE_NAME}: Processing {len(maintenance_metadata)} maintenance event(s) for maintenance_info gauge")
            for idx, maintenance in enumerate(maintenance_metadata):
                # Truncate fields to avoid excessive cardinality
                maintenance_name = maintenance.get('name', 'Unknown')[:100]
                affected = ', '.join(maintenance.get('affected_components', []))[:150]
                maintenance_id = maintenance.get('id', 'unknown')
                scheduled_start = normalize_timestamp(maintenance.get('scheduled_start', 'unknown'))
                scheduled_end = normalize_timestamp(maintenance.get('scheduled_end', 'unknown'))
                shortlink = maintenance.get('shortlink', 'N/A')
                
                logger.debug(f"{SERVICE_NAME}: Maintenance #{idx+1} details:")
                logger.debug(f"  - ID: {maintenance_id}")
                logger.debug(f"  - Name: {maintenance_name}")
                logger.debug(f"  - Scheduled: {scheduled_start} to {scheduled_end}")
                logger.debug(f"  - Shortlink: {shortlink}")
                logger.debug(f"  - Affected: {affected}")
                
                outreach_maintenance_info.labels(
                    service_name=SERVICE_NAME,
                    service_type=SERVICE_TYPE,
                    maintenance_id=maintenance_id,
                    maintenance_name=maintenance_name,
                    scheduled_start=scheduled_start,
                    scheduled_end=scheduled_end,
                    shortlink=shortlink,
                    affected_components=affected
                ).set(1)
                
                logger.debug(f"{SERVICE_NAME}: Set outreach_maintenance_info gauge to 1 for maintenance {maintenance_id}")
                
            logger.info(f"{SERVICE_NAME}: {len(maintenance_metadata)} active maintenance event(s) tracked in maintenance_info gauge")
        else:
            # Set gauge to 0 when there are no maintenance events to always show service status
            logger.debug(f"{SERVICE_NAME}: No maintenance metadata - setting outreach_maintenance_info gauge to 0")
            outreach_maintenance_info.labels(
                service_name=SERVICE_NAME,
                service_type=SERVICE_TYPE,
                maintenance_id='none',
                maintenance_name='No Active Maintenance',
                scheduled_start='N/A',
                scheduled_end='N/A',
                shortlink='N/A',
                affected_components='N/A'
            ).set(0)
    else:
        # Track failed checks in counter metric
        error_type = result.get('raw_status', 'unknown')
        outreach_check_failures_counter.labels(
            service_name=SERVICE_NAME,
            service_type=SERVICE_TYPE,
            error_type=error_type
        ).inc()
    
    logger.info("Outreach monitoring completed")

