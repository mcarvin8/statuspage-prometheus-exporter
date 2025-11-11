"""
Service Monitoring Orchestration Module

This module orchestrates the monitoring of all configured services by iterating
through the service definitions, checking their status, and updating Prometheus
metrics with the results.

Functions:
    - monitor_services: Main orchestration function that coordinates status checks
      for all services and updates Prometheus gauges

Process Flow:
    1. Clear existing Prometheus gauge labels to prevent stale metrics
    2. Iterate through all services defined in services.json
    3. Check each service's status using appropriate checker function
    4. Update Prometheus metrics with status, response time, and details
    5. Track failed checks in a separate counter metric
    6. Log results for operational visibility

Metrics Updated:
    - statuspage_status_gauge: Service health status (-1=incident, 0=maintenance, 1=operational)
        Simplified to just service_name and status value - incident details in statuspage_incident_info
    - statuspage_response_time_gauge: API response time in seconds
    - statuspage_incident_info: Active incident metadata (ID, name, impact, shortlink, etc.)
    - statuspage_maintenance_info: Active maintenance metadata (ID, name, schedule, shortlink, etc.)
    - statuspage_check_failures_counter: Counter for failed status checks

The orchestration ensures consistent metric labels and handles both successful
and failed status checks gracefully. Failed checks are logged and counted but
do not trigger incident alerts.
"""
import logging
import re
from service_checker import SERVICES, check_service_status
from gauges import (statuspage_status_gauge, statuspage_response_time_gauge, 
                    statuspage_check_failures_counter, statuspage_incident_info,
                    statuspage_maintenance_info, statuspage_component_status)
logger = logging.getLogger(__name__)

def normalize_timestamp(timestamp_str):
    """
    Normalize ISO 8601 timestamp to seconds precision (remove milliseconds).
    This prevents duplicate gauge entries due to timestamp precision differences.
    
    Args:
        timestamp_str: ISO 8601 timestamp string (e.g., '2025-11-04T13:25:38.181Z' or '2025-11-04T13:25:38.000Z')
        
    Returns:
        Normalized timestamp string with seconds precision (e.g., '2025-11-04T13:25:38Z')
    """
    if not timestamp_str or timestamp_str == 'N/A' or timestamp_str == 'unknown':
        return timestamp_str
    
    # Remove milliseconds by replacing .XXX pattern before Z or timezone offset
    # Matches patterns like: .181Z, .000Z, .123+00:00, etc.
    normalized = re.sub(r'\.\d{3}(?=[Z\+\-])', '', timestamp_str)
    return normalized

def monitor_services():
    """
    Monitor all configured services and update Prometheus metrics.
    """
    logger.info("Starting status page services monitoring...")
    
    # Step 1: Collect all status check results first
    results = []
    for service_key, service_config in SERVICES.items():
        logger.info(f"Checking {service_config['name']} ({service_key})...")
        
        result = check_service_status(service_key, service_config)
        
        # Store result with service config for later processing
        results.append({
            'service_key': service_key,
            'service_config': service_config,
            'result': result
        })
        
        # Log result immediately
        if result['success']:
            logger.info(f"{service_config['name']}: {result['raw_status']} "
                       f"(response time: {result['response_time']:.2f}s)")
        else:
            logger.warning(f"{service_config['name']}: Check failed ({result.get('raw_status', 'unknown')}), skipping gauge update - {result.get('error', 'Unknown error')}")
    
    # Step 2: Clear all existing gauge labels to remove stale metrics
    # This happens right before updating, minimizing the empty window
    logger.debug("Clearing existing gauge labels before updating with new data...")
    statuspage_status_gauge.clear()
    statuspage_response_time_gauge.clear()
    statuspage_incident_info.clear()  # Clear old incident metadata
    statuspage_maintenance_info.clear()  # Clear old maintenance metadata
    statuspage_component_status.clear()  # Clear old component metadata
    
    # Step 3: Update all gauges with collected results
    for item in results:
        service_key = item['service_key']
        service_config = item['service_config']
        result = item['result']
        
        service_name = service_config['name']
        service_type = service_config['type']
        status_value = result.get('status')
        status_text = result.get('status_text', 'Unknown')
        details = result.get('details', 'No details available')
        
        logger.debug(f"Updating gauge for {service_name}: status={status_value} ({status_text}), details='{details}'")
        
        # Only update gauges if status check succeeded or returned a valid status
        # Skip gauge updates for HTTPS request failures (status=None)
        if status_value is not None:
            # Update main status gauge - simplified to just service_name and status value
            # All incident details are tracked separately in statuspage_incident_info
            statuspage_status_gauge.labels(
                service_name=service_name,
                service_type=service_type
            ).set(status_value)
            
            statuspage_response_time_gauge.labels(
                service_name=service_name,
                service_type=service_type
            ).set(result['response_time'])
            
            # Update incident metadata gauge for each active incident
            incident_metadata = result.get('incident_metadata', [])
            if incident_metadata:
                logger.debug(f"{service_name}: Processing {len(incident_metadata)} incident(s) for incident_info gauge")
                for idx, incident in enumerate(incident_metadata):
                    # Truncate fields to avoid excessive cardinality
                    incident_name = incident.get('name', 'Unknown')[:100]
                    affected = ', '.join(incident.get('affected_components', []))[:150]
                    incident_id = incident.get('id', 'unknown')
                    impact = incident.get('impact', 'unknown')
                    shortlink = incident.get('shortlink', 'N/A')
                    started_at = normalize_timestamp(incident.get('started_at', 'unknown'))
                    
                    logger.debug(f"{service_name}: Incident #{idx+1} details:")
                    logger.debug(f"  - ID: {incident_id}")
                    logger.debug(f"  - Name: {incident_name}")
                    logger.debug(f"  - Impact: {impact}")
                    logger.debug(f"  - Shortlink: {shortlink}")
                    logger.debug(f"  - Started: {started_at}")
                    logger.debug(f"  - Affected: {affected}")
                    
                    statuspage_incident_info.labels(
                        service_name=service_name,
                        service_type=service_type,
                        incident_id=incident_id,
                        incident_name=incident_name,
                        impact=impact,
                        shortlink=shortlink,
                        started_at=started_at,
                        affected_components=affected
                    ).set(1)
                    
                    logger.debug(f"{service_name}: Set statuspage_incident_info gauge to 1 for incident {incident_id}")
                    
                logger.info(f"{service_config['name']}: {len(incident_metadata)} active incident(s) tracked in incident_info gauge")
            else:
                # Set gauge to 0 when there are no incidents to always show service status
                logger.debug(f"{service_name}: No incident metadata - setting statuspage_incident_info gauge to 0")
                statuspage_incident_info.labels(
                    service_name=service_name,
                    service_type=service_type,
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
                logger.debug(f"{service_name}: Processing {len(maintenance_metadata)} maintenance event(s) for maintenance_info gauge")
                for idx, maintenance in enumerate(maintenance_metadata):
                    # Truncate fields to avoid excessive cardinality
                    maintenance_name = maintenance.get('name', 'Unknown')[:100]
                    affected = ', '.join(maintenance.get('affected_components', []))[:150]
                    maintenance_id = maintenance.get('id', 'unknown')
                    scheduled_start = normalize_timestamp(maintenance.get('scheduled_start', 'unknown'))
                    scheduled_end = normalize_timestamp(maintenance.get('scheduled_end', 'unknown'))
                    shortlink = maintenance.get('shortlink', 'N/A')
                    
                    logger.debug(f"{service_name}: Maintenance #{idx+1} details:")
                    logger.debug(f"  - ID: {maintenance_id}")
                    logger.debug(f"  - Name: {maintenance_name}")
                    logger.debug(f"  - Scheduled: {scheduled_start} to {scheduled_end}")
                    logger.debug(f"  - Shortlink: {shortlink}")
                    logger.debug(f"  - Affected: {affected}")
                    
                    statuspage_maintenance_info.labels(
                        service_name=service_name,
                        service_type=service_type,
                        maintenance_id=maintenance_id,
                        maintenance_name=maintenance_name,
                        scheduled_start=scheduled_start,
                        scheduled_end=scheduled_end,
                        shortlink=shortlink,
                        affected_components=affected
                    ).set(1)
                    
                    logger.debug(f"{service_name}: Set statuspage_maintenance_info gauge to 1 for maintenance {maintenance_id}")
                    
                logger.info(f"{service_config['name']}: {len(maintenance_metadata)} active maintenance event(s) tracked in maintenance_info gauge")
            else:
                # Set gauge to 0 when there are no maintenance events to always show service status
                logger.debug(f"{service_name}: No maintenance metadata - setting statuspage_maintenance_info gauge to 0")
                statuspage_maintenance_info.labels(
                    service_name=service_name,
                    service_type=service_type,
                    maintenance_id='none',
                    maintenance_name='No Active Maintenance',
                    scheduled_start='N/A',
                    scheduled_end='N/A',
                    shortlink='N/A',
                    affected_components='N/A'
                ).set(0)
            
            # Update component status gauge for each component
            component_metadata = result.get('component_metadata', [])
            if component_metadata:
                logger.debug(f"{service_name}: Processing {len(component_metadata)} component(s) for component_status gauge")
                for idx, component in enumerate(component_metadata):
                    component_name = component.get('name', 'Unknown')
                    component_status_value = component.get('status_value', 0)
                    component_status_text = component.get('status', 'unknown')
                    
                    logger.debug(f"{service_name}: Component #{idx+1} details:")
                    logger.debug(f"  - Name: {component_name}")
                    logger.debug(f"  - Status: {component_status_text} (value: {component_status_value})")
                    
                    statuspage_component_status.labels(
                        service_name=service_name,
                        component_name=component_name
                    ).set(component_status_value)
                    
                    logger.debug(f"{service_name}: Set statuspage_component_status gauge to {component_status_value} for component '{component_name}'")
                
                logger.info(f"{service_config['name']}: {len(component_metadata)} component(s) tracked in component_status gauge")
            else:
                logger.debug(f"{service_name}: No component metadata available")
        else:
            # Track failed checks in counter metric
            error_type = result.get('raw_status', 'unknown')
            statuspage_check_failures_counter.labels(
                service_name=service_name,
                service_type=service_type,
                error_type=error_type
            ).inc()
    
    logger.info("Status page services monitoring completed")
