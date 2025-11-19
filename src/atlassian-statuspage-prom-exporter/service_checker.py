"""
Service Status Checking Module

This module provides functions for checking the operational status of external
business applications and SaaS services. It supports multiple service types
and status page formats.

Supported Service Types:
    - status_page: StatusPage.io format (Atlassian)
    - Extensible architecture for additional types (Pingdom, custom APIs, etc.)

Configuration:
    - Service definitions loaded from services.json
    - Each service includes: name, type, URL, and other type-specific config

Functions:
    - check_status_page_service: Checks StatusPage.io API format
    - check_service_status: Main dispatcher that routes to appropriate checker

Incident Handling:
    - Filters incidents to only ACTIVE ones (excludes resolved/completed/postmortem)
    - Checks resolved_at timestamp to ensure incident is still ongoing
    - When multiple active incidents exist, their messages are merged with affected components
    - The highest severity from all active incidents is applied to the gauge
    - Severity priority: critical > major > minor > none
    - Incident details include affected component names

Component Monitoring:
    - Checks all components for operational status
    - Non-operational components trigger alerts even without active incidents
    - Component names are included in alert details for better context
    - Partial outages (some components down) are detected and reported
    - Component-level status is tracked in separate Prometheus gauge (bizapps_component_status)
    - Each component status is mapped: operational=1, degraded/outage=-1, maintenance=0

Status Mapping:
    StatusPage.io indicators mapped to numeric values:
    - 'none': 1 (All systems operational)
    - 'minor': -1 (Minor service outage / degraded)
    - 'major': -1 (Major service outage)
    - 'critical': -1 (Critical service outage)
    - 'maintenance': 0 (Scheduled maintenance)

Return Format:
    All check functions return a dictionary with:
    - status: Numeric status value (1=operational, 0=maintenance, -1=incident, None=check failed)
    - response_time: API response time in seconds
    - raw_status: Raw status indicator from API
    - status_text: Human-readable status text
    - details: Detailed status description (merged incident names with metadata)
    - success: Boolean indicating if check succeeded
    - error: Error message (if success=False)
    - incident_metadata: List of dicts with incident details (ID, shortlink, duration, etc.)
    - maintenance_metadata: List of dicts with maintenance details (ID, schedule, shortlink, etc.)
    - component_metadata: List of dicts with component details (name, status, status_value)

Error Handling:
    - Network errors (timeouts, connection failures) with automatic retry (3 attempts)
    - Exponential backoff between retries (0.5s base factor)
    - Retries on: read timeouts, connection timeouts, and 5xx HTTP status codes
    - Request failures (network, timeout, HTTP errors) return status=None (no gauge update)
    - JSON parsing errors return status=None (likely temporary API issue)
    - Configuration errors return status=None (not a service incident)
    - All errors are logged with descriptive error messages
"""
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import time
from typing import Dict, Any
from cache_manager import save_service_response

# Load services configuration
import os
config_path = os.path.join(os.path.dirname(__file__), 'services.json')
with open(config_path, 'r') as f:
    SERVICES = json.load(f)

logger = logging.getLogger(__name__)

def create_retry_session(retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504)):
    """
    Create a requests session with retry logic.
    
    Args:
        retries: Number of retry attempts (default: 3)
        backoff_factor: Backoff factor for exponential delay between retries (default: 0.5)
        status_forcelist: HTTP status codes to retry on (default: 500, 502, 503, 504)
        
    Returns:
        requests.Session object configured with retry adapter
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        read=retries,  # Retry on read timeouts
        connect=retries,  # Retry on connection timeouts
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD", "OPTIONS"]  # Safe methods to retry
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def check_status_page_service(service_key: str, service_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check status page service using statuspage.io API format.
    
    Args:
        service_key: Key identifier for the service
        service_config: Service configuration dictionary
        
    Returns:
        Dictionary with status information
    """
    try:
        logger.debug(f"Status page service {service_key}: Checking {service_config['url']}")
        
        # Create session with retry logic
        session = create_retry_session(retries=3, backoff_factor=0.5)
        
        start_time = time.time()
        response = session.get(
            service_config['url'],
            timeout=15,
            headers={'User-Agent': 'AtlassianStatusPageExporter/1.0'}
        )
        response.raise_for_status()
        
        response_time = time.time() - start_time
        logger.debug(f"Status page service {service_key}: API responded in {response_time:.2f}s")
        
        # Parse JSON response
        data = response.json()
        
        # Extract status information from statuspage.io format
        status = data.get('status', {})
        indicator = status.get('indicator', 'unknown')
        description = status.get('description', 'No description available')
        
        # Get all components and check for non-operational ones
        components = data.get('components', [])
        non_operational_components = [
            c for c in components 
            if c.get('status', '').lower() != 'operational'
        ]
        
        # Extract component metadata for component-level monitoring
        component_metadata = []
        for comp in components:
            component_name = comp.get('name', 'Unknown')
            component_status = comp.get('status', 'unknown').lower()
            
            # Map component status to numeric value
            # StatusPage.io component statuses: operational, degraded, partial_outage, major_outage, under_maintenance
            if component_status == 'operational':
                status_value = 1
            elif component_status in ['degraded', 'partial_outage', 'major_outage', 'degraded_performance']:
                status_value = -1
            elif component_status in ['under_maintenance', 'maintenance']:
                status_value = 0
            else:
                status_value = 0  # Unknown status defaults to 0
            
            component_metadata.append({
                'name': component_name,
                'status': component_status,
                'status_value': status_value
            })
            
            logger.debug(f"Status page service {service_key}: Component '{component_name}': {component_status} (value: {status_value})")
        
        logger.debug(f"Status page service {service_key}: Extracted {len(component_metadata)} component(s)")
        
        # Filter incidents to only ACTIVE ones (exclude resolved/completed/postmortem)
        terminal_statuses = {'resolved', 'completed', 'postmortem'}
        all_incidents = data.get('incidents', [])
        active_incidents = [
            inc for inc in all_incidents
            if inc.get('status', '').lower() not in terminal_statuses 
            and not inc.get('resolved_at')
        ]
        
        logger.debug(f"Status page service {service_key}: Total incidents: {len(all_incidents)}, Active: {len(active_incidents)}, Non-operational components: {len(non_operational_components)}")
        
        # Collect metadata for active incidents
        incident_metadata = []
        maintenance_metadata = []
        
        # Check for scheduled/active maintenance
        scheduled_maintenances = data.get('scheduled_maintenances', [])
        active_maintenances = [
            maint for maint in scheduled_maintenances
            if maint.get('status', '').lower() not in {'completed', 'cancelled'}
            and not maint.get('resolved_at')
        ]
        
        logger.debug(f"Status page service {service_key}: Total maintenances: {len(scheduled_maintenances)}, Active: {len(active_maintenances)}")
        
        logger.debug(f"Status page service {service_key}: Building incident metadata for {len(active_incidents)} active incident(s)")
        
        # Check for active incidents and extract their names for more detailed information
        if active_incidents:
            # Deduplicate incidents by ID (in case API returns duplicates with slightly different timestamps)
            seen_incident_ids = set()
            unique_incidents = []
            for inc in active_incidents:
                incident_id = inc.get('id', 'unknown')
                if incident_id not in seen_incident_ids:
                    seen_incident_ids.add(incident_id)
                    unique_incidents.append(inc)
                else:
                    logger.debug(f"Status page service {service_key}: Skipping duplicate incident {incident_id}")
            
            logger.debug(f"Status page service {service_key}: Found {len(active_incidents)} active incident(s), {len(unique_incidents)} unique after deduplication")
            
            # Get all active incident names and affected components
            # Extract base URL from service config to construct incident URLs if shortlink is missing
            service_url = service_config.get('url', '')
            base_url = service_url.replace('/api/v2/summary.json', '').rstrip('/') if service_url else ''
            
            incident_details = []
            for inc in unique_incidents:
                name = inc.get('name', 'Unnamed incident')
                incident_id = inc.get('id', 'unknown')
                shortlink = inc.get('shortlink', '')
                
                # If shortlink is missing, construct incident URL from base URL and incident ID
                if not shortlink and base_url and incident_id != 'unknown':
                    shortlink = f"{base_url}/incidents/{incident_id}"
                    logger.debug(f"Status page service {service_key}: Constructed incident URL from ID: {shortlink}")
                
                started_at = inc.get('started_at') or inc.get('created_at', '')
                updated_at = inc.get('updated_at', '')
                impact = inc.get('impact', 'unknown')
                incident_status = inc.get('status', 'unknown')
                
                affected_comps = [c.get('name', '') for c in inc.get('components', [])]
                
                # Build metadata dict
                metadata = {
                    'id': incident_id,
                    'name': name,
                    'status': incident_status,
                    'impact': impact,
                    'started_at': started_at,
                    'updated_at': updated_at,
                    'shortlink': shortlink,
                    'affected_components': affected_comps
                }
                incident_metadata.append(metadata)
                
                logger.debug(f"Status page service {service_key}: Incident metadata collected:")
                logger.debug(f"  ID: {incident_id}, Name: {name}, Impact: {impact}")
                logger.debug(f"  Shortlink: {shortlink}, Started: {started_at}")
                logger.debug(f"  Affected components: {affected_comps}")
                
                # Build human-readable detail string with link
                if affected_comps:
                    detail = f"{name} (affects: {', '.join(affected_comps)})"
                else:
                    detail = name
                
                if shortlink:
                    detail = f"{detail} - {shortlink}"
                    
                incident_details.append(detail)
            
            # Use the incident details as the description (more specific than status.description)
            description = '; '.join(incident_details)
            logger.debug(f"Status page service {service_key}: Found {len(active_incidents)} active incident(s): {description}")
            logger.info(f"Status page service {service_key}: Returning {len(incident_metadata)} incident metadata records")
            
            # Determine highest severity from all active incidents
            # Severity priority: critical > major > minor
            severity_priority = {
                'critical': 3,
                'major': 2,
                'minor': 1,
                'none': 0
            }
            
            highest_severity = 'none'
            highest_priority = 0
            
            for inc in active_incidents:
                inc_impact = inc.get('impact', 'none').lower()
                inc_priority = severity_priority.get(inc_impact, 0)
                if inc_priority > highest_priority:
                    highest_priority = inc_priority
                    highest_severity = inc_impact
            
            # Override the indicator with the highest severity found
            if highest_severity != 'none':
                indicator = highest_severity
                logger.debug(f"Status page service {service_key}: Overriding indicator to '{indicator}' based on highest incident severity")
        
        # Also check non-operational components as a separate signal
        if non_operational_components and not active_incidents:
            # Components are down but no active incidents reported
            component_names = [c.get('name', 'Unknown') for c in non_operational_components]
            description = f"Non-operational components: {'; '.join(component_names)}"
            indicator = 'minor'  # Default to minor if components down but no incident severity
            logger.warning(f"Status page service {service_key}: {len(non_operational_components)} components non-operational but no active incidents")
        
        # Collect maintenance metadata
        if active_maintenances:
            logger.debug(f"Status page service {service_key}: Building maintenance metadata for {len(active_maintenances)} active maintenance(s)")
            
            # Deduplicate maintenance events by ID (in case API returns duplicates with slightly different timestamps)
            seen_maintenance_ids = set()
            unique_maintenances = []
            for maint in active_maintenances:
                maintenance_id = maint.get('id', 'unknown')
                if maintenance_id not in seen_maintenance_ids:
                    seen_maintenance_ids.add(maintenance_id)
                    unique_maintenances.append(maint)
                else:
                    logger.debug(f"Status page service {service_key}: Skipping duplicate maintenance {maintenance_id}")
            
            logger.debug(f"Status page service {service_key}: Found {len(active_maintenances)} active maintenance(s), {len(unique_maintenances)} unique after deduplication")
            
            for maint in unique_maintenances:
                maintenance_id = maint.get('id', 'unknown')
                name = maint.get('name', 'Unnamed maintenance')
                scheduled_start = maint.get('scheduled_for', '') or maint.get('created_at', '')
                scheduled_end = maint.get('scheduled_until', '') or maint.get('scheduled_for', '')
                shortlink = maint.get('shortlink', '')
                maintenance_status = maint.get('status', 'unknown')
                
                affected_comps = [c.get('name', '') for c in maint.get('components', [])]
                
                # Build metadata dict
                metadata = {
                    'id': maintenance_id,
                    'name': name,
                    'status': maintenance_status,
                    'scheduled_start': scheduled_start,
                    'scheduled_end': scheduled_end,
                    'shortlink': shortlink,
                    'affected_components': affected_comps
                }
                maintenance_metadata.append(metadata)
                
                logger.debug(f"Status page service {service_key}: Maintenance metadata collected:")
                logger.debug(f"  ID: {maintenance_id}, Name: {name}, Status: {maintenance_status}")
                logger.debug(f"  Scheduled: {scheduled_start} to {scheduled_end}")
                logger.debug(f"  Shortlink: {shortlink}, Affected components: {affected_comps}")
        
        logger.debug(f"Status page service {service_key}: indicator='{indicator}', description='{description}'")
        
        # Map statuspage.io indicators to our status values
        status_mapping = {
            'none': 1,           # All systems operational
            'minor': -1,         # Minor service outage/degradation
            'major': -1,         # Major service outage
            'critical': -1,      # Critical service outage
            'maintenance': 0     # Maintenance mode
        }
        
        status_value = status_mapping.get(indicator.lower(), 0)
        
        # Determine status text based on indicator
        status_text_mapping = {
            'none': 'Operational',
            'minor': 'Minor Outage',
            'major': 'Major Outage',
            'critical': 'Critical Outage',
            'maintenance': 'Maintenance'
        }
        
        status_text = status_text_mapping.get(indicator.lower(), 'Unknown')
        
        logger.debug(f"Status page service {service_key}: Final result - status_value={status_value}, status_text='{status_text}'")
        
        result = {
            'status': status_value,
            'response_time': response_time,
            'raw_status': indicator,
            'status_text': status_text,
            'details': description,
            'success': True,
            'incident_metadata': incident_metadata,  # List of incident details with metadata
            'maintenance_metadata': maintenance_metadata,  # List of maintenance details with metadata
            'component_metadata': component_metadata  # List of component details with status
        }
        
        # Save successful response to cache for fallback on future failures
        save_service_response(service_key, result)
        
        return result
        
    except requests.exceptions.HTTPError as e:
        # HTTP errors (4xx, 5xx) - categorize for better tracking
        status_code = e.response.status_code if e.response is not None else 0
        
        if status_code == 404:
            error_type = 'http_404_not_found'
            logger.error(f"Configuration error for {service_key}: 404 Not Found - Check URL in services.json")
        elif status_code == 401 or status_code == 403:
            error_type = 'http_auth_error'
            logger.error(f"Authentication error for {service_key}: {status_code}")
        elif 400 <= status_code < 500:
            error_type = f'http_4xx_error'
            logger.error(f"Client error for {service_key}: {status_code} - {e}")
        elif 500 <= status_code < 600:
            error_type = f'http_5xx_error'
            logger.warning(f"Server error for {service_key}: {status_code} - Status page API may be down")
        else:
            error_type = 'http_error'
            logger.error(f"HTTP error for {service_key}: {e}")
        
        return {
            'status': None,  # Don't set gauge on HTTP errors
            'response_time': 0,
            'raw_status': error_type,
            'status_text': 'HTTP Error',
            'details': f"HTTP {status_code}: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'component_metadata': []
        }
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout error for {service_key}: {e}")
        return {
            'status': None,  # Don't set gauge on timeout
            'response_time': 0,
            'raw_status': 'timeout',
            'status_text': 'Timeout',
            'details': f"Request timeout: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'component_metadata': []
        }
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error for {service_key}: {e}")
        return {
            'status': None,  # Don't set gauge on connection failures
            'response_time': 0,
            'raw_status': 'connection_error',
            'status_text': 'Connection Error',
            'details': f"Connection failed: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'component_metadata': []
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {service_key}: {e}")
        return {
            'status': None,  # Don't set gauge on request failures
            'response_time': 0,
            'raw_status': 'request_error',
            'status_text': 'Request Error',
            'details': f"Request failed: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'component_metadata': []
        }
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {service_key}: {e}")
        return {
            'status': None,  # Don't set gauge on JSON parse failures
            'response_time': 0,
            'raw_status': 'json_error',
            'status_text': 'Parse Error',
            'details': f"Invalid JSON response: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'component_metadata': []
        }
    except Exception as e:
        logger.error(f"Unexpected error for {service_key}: {e}")
        return {
            'status': None,  # Don't set gauge on unexpected errors
            'response_time': 0,
            'raw_status': 'unknown_error',
            'status_text': 'Unknown Error',
            'details': f"Unexpected error: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': []
        }

def check_service_status(service_key: str, service_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check the status of a single service.
    
    Args:
        service_key: Key identifier for the service
        service_config: Service configuration dictionary
        
    Returns:
        Dictionary with status information
    """
    return check_status_page_service(service_key, service_config)
