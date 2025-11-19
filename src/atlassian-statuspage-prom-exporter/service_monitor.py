"""
Service Monitoring Orchestration Module

This module orchestrates the monitoring of all configured services
by iterating through the service definitions, checking their status, and updating
Prometheus metrics with the results.

Functions:
    - monitor_services: Main orchestration function that coordinates
      status checks for all services and updates Prometheus gauges

Process Flow:
    1. Iterate through all services defined in services.json and collect status check results
    2. For failed requests, attempt to load cached response data as fallback
    3. Clear existing Prometheus gauge labels (response_time only - others updated selectively)
    4. Update all gauges with collected results
    5. For incident, maintenance, status, and component gauges: Only update when they change per service (prevents unnecessary updates)
    6. Response time gauge always updates (dynamic metric for trending)
    7. Failed checks are logged (check logs for failure details)
    
    Incident Gauge Strategy:
    - Incident gauge is NOT cleared globally (unlike other gauges)
    - For each service, compare current incidents with cached incidents
    - Only update incident gauge when incidents have changed (added, removed, or updated)
    - Clear resolved incidents by setting them to 0 (using cached metadata to match labels)
    - If no cache exists, update normally (first run or cache cleared)
    - This prevents unnecessary gauge writes and alert churn while ensuring accuracy
    
    Maintenance Gauge Strategy:
    - Maintenance gauge is NOT cleared globally (unlike other gauges)
    - For each service, compare current maintenance with cached maintenance
    - Only update maintenance gauge when maintenance has changed (added, removed, or updated)
    - Clear resolved maintenance by setting them to 0 (using cached metadata to match labels)
    - If no cache exists, update normally (first run or cache cleared)
    - This prevents unnecessary gauge writes and alert churn while ensuring accuracy
    
    Status Gauge Strategy:
    - Status gauge is NOT cleared globally (unlike response_time gauge)
    - For each service, compare current status with cached status
    - Only update status gauge when status has changed (operational/maintenance/incident transitions)
    - If no cache exists, update normally (first run or cache cleared)
    - This prevents unnecessary gauge writes while ensuring accuracy
    
    Component Status Gauge Strategy:
    - Component status gauge is NOT cleared globally (unlike response_time gauge)
    - For each service, compare current components with cached components
    - Only update component gauge when components have changed (added, removed, or status changed)
    - Clear removed components by setting them to 0 (using cached metadata to match labels)
    - If no cache exists, update normally (first run or cache cleared)
    - This prevents unnecessary gauge writes while ensuring accuracy
    
    Response Time Gauge Strategy:
    - Response time gauge is cleared and updated every run
    - Response times are dynamic and should be tracked continuously for performance trending
    - This metric is not used for alerts, so frequent updates are acceptable
    
    Cache Fallback Strategy:
    - When an API request fails, the service attempts to load the last successful
      response from cache
    - If cached data exists, it's used to update metrics, preventing alerts from
      clearing and re-firing due to transient network issues
    - This ensures continuity of monitoring even when individual requests fail

Metrics Updated:
    - statuspage_status_gauge: Service health status (-1=incident, 0=maintenance, 1=operational)
        Simplified to just service_name and status value - incident details in statuspage_incident_info
        Only updated when status changes per service to prevent unnecessary updates
    - statuspage_response_time_gauge: API response time in seconds
        Always updated every run (dynamic metric for performance trending)
    - statuspage_incident_info: Active incident metadata (ID, name, impact, shortlink, etc.)
        Only updated when incidents change per service to prevent unnecessary updates
    - statuspage_maintenance_info: Active maintenance metadata (ID, name, schedule, shortlink, etc.)
        Only updated when maintenance changes per service to prevent unnecessary updates
    - statuspage_component_status: Individual component status (1=operational, 0=maintenance, -1=degraded/down)
        Only updated when components change per service to prevent unnecessary updates

The orchestration ensures consistent metric labels and handles both successful
and failed status checks gracefully. Failed checks fall back to cached data when
available, preventing alert churn from transient failures.
"""
import logging
import re
from service_checker import SERVICES, check_service_status
from gauges import (statuspage_status_gauge, statuspage_response_time_gauge, 
                    statuspage_incident_info,
                    statuspage_maintenance_info, statuspage_component_status)
from cache_manager import load_service_response

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
    
    Process Flow:
    1. Collect status check results for all services first
    2. Clear existing Prometheus gauge labels to remove stale metrics
    3. Immediately update all gauges with collected results
    
    This minimizes the window where Prometheus might scrape empty gauges
    by collecting all data before clearing and updating.
    """
    logger.info("Starting status page services monitoring...")
    
    # Step 1: Collect all status check results first
    # Load previous cache for each service BEFORE checking (to compare against old state)
    previous_caches = {}
    for service_key in SERVICES.keys():
        previous_caches[service_key] = load_service_response(service_key)
    
    results = []
    for service_key, service_config in SERVICES.items():
        logger.info(f"Checking {service_config['name']} ({service_key})...")
        
        result = check_service_status(service_key, service_config)
        original_failure = None
        
        # If request failed, try to load cached response as fallback
        if not result['success']:
            # Store original failure info for tracking
            original_failure = {
                'raw_status': result.get('raw_status', 'unknown'),
                'error': result.get('error', 'Unknown error')
            }
            
            logger.warning(f"{service_config['name']}: Check failed ({original_failure['raw_status']}), attempting to load cached response...")
            cached_result = load_service_response(service_key)
            
            if cached_result:
                logger.info(f"{service_config['name']}: Using cached response data (from previous successful check)")
                # Mark that this is cached data (for logging/metrics)
                result = cached_result.copy()
                result['from_cache'] = True
                result['original_failure'] = original_failure  # Preserve failure info for logging
            else:
                logger.warning(f"{service_config['name']}: No cached data available, will skip gauge update - {original_failure['error']}")
                result['from_cache'] = False
                result['original_failure'] = original_failure
        else:
            # Successful request - cache will be saved by service_checker
            result['from_cache'] = False
            result['original_failure'] = None
        
        # Store result with service config for later processing
        results.append({
            'service_key': service_key,
            'service_config': service_config,
            'result': result
        })
        
        # Log result immediately
        cache_note = " (from cache)" if result.get('from_cache', False) else ""
        if result['success'] or result.get('from_cache', False):
            logger.info(f"{service_config['name']}: {result['raw_status']} "
                       f"(response time: {result['response_time']:.2f}s){cache_note}")
        else:
            logger.warning(f"{service_config['name']}: Check failed ({result.get('raw_status', 'unknown')}), no cached data available - {result.get('error', 'Unknown error')}")
    
    # Step 2: Clear all existing gauge labels to remove stale metrics
    # This happens right before updating, minimizing the empty window
    # Note: statuspage_incident_info, statuspage_maintenance_info, statuspage_status_gauge, and statuspage_component_status
    # are NOT cleared - updated selectively per service when they change
    logger.debug("Clearing existing gauge labels before updating with new data...")
    # statuspage_status_gauge is NOT cleared - updated selectively per service
    statuspage_response_time_gauge.clear()  # Response time always updates (dynamic metric)
    # statuspage_incident_info is NOT cleared - updated selectively per service
    # statuspage_maintenance_info is NOT cleared - updated selectively per service
    # statuspage_component_status is NOT cleared - updated selectively per service
    
    # Step 3: Update all gauges with collected results
    for item in results:
        service_key = item['service_key']
        service_config = item['service_config']
        result = item['result']
        
        service_name = service_config['name']
        status_value = result.get('status')
        status_text = result.get('status_text', 'Unknown')
        details = result.get('details', 'No details available')
        original_failure = result.get('original_failure')
        from_cache = result.get('from_cache', False)
        logger.debug(f"Updating gauge for {service_name}: status={status_value} ({status_text}), details='{details}', from_cache={from_cache}")
        
        # Only update gauges if status check succeeded or returned a valid status
        # Skip gauge updates for HTTPS request failures (status=None)
        if status_value is not None:
            # Update response time gauge - always update (dynamic metric)
            statuspage_response_time_gauge.labels(
                service_name=service_name
            ).set(result['response_time'])
            
            # Update main status gauge - only when status changes
            # Use previous cache (from before this run) to compare status
            cached_data = previous_caches.get(service_key)
            has_cache = cached_data is not None
            
            # Determine if status has changed
            status_has_changed = True  # Default to True (update if no cache)
            
            if has_cache:
                cached_status = cached_data.get('status')
                if cached_status == status_value:
                    # Same status - no change
                    status_has_changed = False
                else:
                    # Status changed
                    status_has_changed = True
                    logger.info(f"{service_name}: Status changed from {cached_status} to {status_value}")
            else:
                # No cache exists - first run or cache cleared
                logger.debug(f"{service_name}: No cache found - updating status gauge (first run or cache cleared)")
            
            if status_has_changed:
                # Update main status gauge - simplified to just service_name and status value
                # All incident details are tracked separately in statuspage_incident_info
                statuspage_status_gauge.labels(
                    service_name=service_name
                ).set(status_value)
                logger.debug(f"{service_name}: Updated status gauge to {status_value}")
            else:
                logger.debug(f"{service_name}: Status unchanged ({status_value}) - skipping status gauge update")
            
            # Update incident metadata gauge - only when incidents change for this service
            # Compare current incidents with cached incidents to avoid unnecessary updates
            incident_metadata = result.get('incident_metadata', [])
            
            # Use previous cache (from before this run) to compare incidents
            # This ensures we compare against the OLD state, not the NEW state we just saved
            cached_data = previous_caches.get(service_key)
            has_cache = cached_data is not None
            
            # Determine if incidents have changed
            incidents_have_changed = True  # Default to True (update if no cache)
            change_type = None  # Track what type of change occurred
            
            if has_cache:
                cached_incidents = cached_data.get('incident_metadata', [])
                
                # Compare incident IDs only (ignore updated_at changes)
                current_ids = {inc.get('id', 'unknown') for inc in incident_metadata}
                cached_ids = {inc.get('id', 'unknown') for inc in cached_incidents}
                
                if current_ids == cached_ids:
                    # Same incident IDs - no changes (ignore updated_at/details changes)
                    incidents_have_changed = False
                else:
                    # Different incident IDs - incidents changed (added or resolved)
                    incidents_have_changed = True
                    added_ids = current_ids - cached_ids
                    removed_ids = cached_ids - current_ids
                    if added_ids and removed_ids:
                        change_type = 'added_and_removed'
                        logger.info(f"{service_name}: Incidents changed - added: {added_ids}, removed: {removed_ids}")
                    elif added_ids:
                        change_type = 'added'
                        logger.info(f"{service_name}: New incident(s) detected: {added_ids}")
                    elif removed_ids:
                        change_type = 'removed'
                        logger.info(f"{service_name}: Incident(s) resolved: {removed_ids}")
            else:
                # No cache exists - first run or cache cleared
                logger.info(f"{service_name}: No cache found - updating incident gauge (first run or cache cleared)")
                change_type = 'no_cache'
            
            if incidents_have_changed:
                if change_type:
                    logger.info(f"{service_name}: Incidents changed ({change_type}), updating incident gauge")
                else:
                    logger.info(f"{service_name}: Incidents changed, updating incident gauge")
                
                # Clear resolved incidents (in cache but not in current) - only if cache exists
                if has_cache:
                    cached_incidents = cached_data.get('incident_metadata', [])
                    current_ids = {inc.get('id', 'unknown') for inc in incident_metadata}
                    cached_ids = {inc.get('id', 'unknown') for inc in cached_incidents}
                    resolved_ids = cached_ids - current_ids
                    
                    if resolved_ids:
                        logger.info(f"{service_name}: Clearing {len(resolved_ids)} resolved incident(s): {resolved_ids}")
                        cached_by_id = {inc.get('id', 'unknown'): inc for inc in cached_incidents}
                        for resolved_id in resolved_ids:
                            resolved_inc = cached_by_id.get(resolved_id, {})
                            # Use cached metadata to match the exact labels that were set
                            resolved_name = resolved_inc.get('name', 'Unknown')[:100]
                            resolved_affected = ', '.join(resolved_inc.get('affected_components', []))[:150]
                            resolved_impact = resolved_inc.get('impact', 'unknown')
                            resolved_shortlink = resolved_inc.get('shortlink', 'N/A')
                            resolved_started = normalize_timestamp(resolved_inc.get('started_at', 'unknown'))
                            
                            statuspage_incident_info.labels(
                                service_name=service_name,
                                incident_id=resolved_id,
                                incident_name=resolved_name,
                                impact=resolved_impact,
                                shortlink=resolved_shortlink,
                                started_at=resolved_started,
                                affected_components=resolved_affected
                            ).set(0)
                            
                            logger.debug(f"{service_name}: Set resolved incident {resolved_id} to 0")
                
                # Update current active incidents
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
                        incident_id='none',
                        incident_name='No Active Incidents',
                        impact='none',
                        shortlink='N/A',
                        started_at='N/A',
                        affected_components='N/A'
                    ).set(0)
            else:
                # Scenario 2: Cache exists, incidents unchanged
                logger.info(f"{service_name}: Incidents unchanged (same IDs, no updates) - skipping incident gauge update")
            
            # Update maintenance metadata gauge - only when maintenance changes for this service
            # Compare current maintenance with cached maintenance to avoid unnecessary updates
            maintenance_metadata = result.get('maintenance_metadata', [])
            
            # Use previous cache (from before this run) to compare maintenance
            # This ensures we compare against the OLD state, not the NEW state we just saved
            cached_data = previous_caches.get(service_key)
            has_cache = cached_data is not None
            
            # Determine if maintenance has changed
            maintenance_has_changed = True  # Default to True (update if no cache)
            change_type = None  # Track what type of change occurred
            
            if has_cache:
                cached_maintenance = cached_data.get('maintenance_metadata', [])
                
                # Compare maintenance IDs only (ignore updated_at changes)
                current_ids = {maint.get('id', 'unknown') for maint in maintenance_metadata}
                cached_ids = {maint.get('id', 'unknown') for maint in cached_maintenance}
                
                if current_ids == cached_ids:
                    # Same maintenance IDs - no changes (ignore updated_at/details changes)
                    maintenance_has_changed = False
                else:
                    # Different maintenance IDs - maintenance changed (added or resolved)
                    maintenance_has_changed = True
                    added_ids = current_ids - cached_ids
                    removed_ids = cached_ids - current_ids
                    if added_ids and removed_ids:
                        change_type = 'added_and_removed'
                        logger.info(f"{service_name}: Maintenance changed - added: {added_ids}, removed: {removed_ids}")
                    elif added_ids:
                        change_type = 'added'
                        logger.info(f"{service_name}: New maintenance event(s) detected: {added_ids}")
                    elif removed_ids:
                        change_type = 'removed'
                        logger.info(f"{service_name}: Maintenance event(s) resolved: {removed_ids}")
            else:
                # No cache exists - first run or cache cleared
                logger.info(f"{service_name}: No cache found - updating maintenance gauge (first run or cache cleared)")
                change_type = 'no_cache'
            
            if maintenance_has_changed:
                if change_type:
                    logger.info(f"{service_name}: Maintenance changed ({change_type}), updating maintenance gauge")
                else:
                    logger.info(f"{service_name}: Maintenance changed, updating maintenance gauge")
                
                # Clear resolved maintenance (in cache but not in current) - only if cache exists
                if has_cache:
                    cached_maintenance = cached_data.get('maintenance_metadata', [])
                    current_ids = {maint.get('id', 'unknown') for maint in maintenance_metadata}
                    cached_ids = {maint.get('id', 'unknown') for maint in cached_maintenance}
                    resolved_ids = cached_ids - current_ids
                    
                    if resolved_ids:
                        logger.info(f"{service_name}: Clearing {len(resolved_ids)} resolved maintenance event(s): {resolved_ids}")
                        cached_by_id = {maint.get('id', 'unknown'): maint for maint in cached_maintenance}
                        for resolved_id in resolved_ids:
                            resolved_maint = cached_by_id.get(resolved_id, {})
                            # Use cached metadata to match the exact labels that were set
                            resolved_name = resolved_maint.get('name', 'Unknown')[:100]
                            resolved_affected = ', '.join(resolved_maint.get('affected_components', []))[:150]
                            resolved_scheduled_start = normalize_timestamp(resolved_maint.get('scheduled_start', 'unknown'))
                            resolved_scheduled_end = normalize_timestamp(resolved_maint.get('scheduled_end', 'unknown'))
                            resolved_shortlink = resolved_maint.get('shortlink', 'N/A')
                            
                            statuspage_maintenance_info.labels(
                                service_name=service_name,
                                maintenance_id=resolved_id,
                                maintenance_name=resolved_name,
                                scheduled_start=resolved_scheduled_start,
                                scheduled_end=resolved_scheduled_end,
                                shortlink=resolved_shortlink,
                                affected_components=resolved_affected
                            ).set(0)
                            
                            logger.debug(f"{service_name}: Set resolved maintenance {resolved_id} to 0")
                
                # Update current active maintenance
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
                        maintenance_id='none',
                        maintenance_name='No Active Maintenance',
                        scheduled_start='N/A',
                        scheduled_end='N/A',
                        shortlink='N/A',
                        affected_components='N/A'
                    ).set(0)
            else:
                # Scenario 2: Cache exists, maintenance unchanged
                logger.info(f"{service_name}: Maintenance unchanged (same IDs, no updates) - skipping maintenance gauge update")
            
            # Update component status gauge - only when components change
            component_metadata = result.get('component_metadata', [])
            
            # Use previous cache (from before this run) to compare components
            cached_data = previous_caches.get(service_key)
            has_cache = cached_data is not None
            
            # Determine if components have changed
            components_have_changed = True  # Default to True (update if no cache)
            
            if has_cache:
                cached_components = cached_data.get('component_metadata', [])
                
                # Compare components by name and status value
                current_components = {(comp.get('name', 'Unknown'), comp.get('status_value', 0)) for comp in component_metadata}
                cached_components_set = {(comp.get('name', 'Unknown'), comp.get('status_value', 0)) for comp in cached_components}
                
                if current_components == cached_components_set:
                    # Same components with same status - no changes
                    components_have_changed = False
                else:
                    # Components changed (added, removed, or status changed)
                    components_have_changed = True
                    added = current_components - cached_components_set
                    removed = cached_components_set - current_components
                    if added or removed:
                        logger.info(f"{service_name}: Components changed - added/updated: {added}, removed: {removed}")
            else:
                # No cache exists - first run or cache cleared
                logger.debug(f"{service_name}: No cache found - updating component gauge (first run or cache cleared)")
            
            if components_have_changed:
                # Clear removed components (in cache but not in current) - only if cache exists
                if has_cache:
                    cached_components = cached_data.get('component_metadata', [])
                    current_names = {comp.get('name', 'Unknown') for comp in component_metadata}
                    cached_names = {comp.get('name', 'Unknown') for comp in cached_components}
                    removed_names = cached_names - current_names
                    
                    if removed_names:
                        logger.info(f"{service_name}: Clearing {len(removed_names)} removed component(s): {removed_names}")
                        cached_by_name = {comp.get('name', 'Unknown'): comp for comp in cached_components}
                        for removed_name in removed_names:
                            removed_comp = cached_by_name.get(removed_name, {})
                            statuspage_component_status.labels(
                                service_name=service_name,
                                component_name=removed_name
                            ).set(0)  # Set removed components to 0
                            logger.debug(f"{service_name}: Set removed component {removed_name} to 0")
                
                # Update current components
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
                    logger.debug(f"{service_name}: No component metadata - components may have been cleared")
            else:
                # Components unchanged
                logger.debug(f"{service_name}: Components unchanged - skipping component gauge update")
        # Note: Failed checks are logged but not tracked in metrics (check logs for failure details)

    logger.info("Status page services monitoring completed")
