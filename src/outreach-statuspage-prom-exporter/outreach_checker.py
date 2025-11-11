"""
Outreach Status Page Checking Module

This module provides functions for checking the operational status of Outreach
by parsing their HTML status page. Since Outreach doesn't expose a JSON API,
we use Selenium to render the JavaScript-rendered React/MUI page and parse
the HTML to extract component statuses and incident information.

Return Format:
    Returns a dictionary with:
    - status: Numeric status value (1=operational, 0=maintenance, -1=incident, None=check failed)
    - response_time: Response time in seconds (includes JavaScript rendering)
    - raw_status: Raw status indicator
    - status_text: Human-readable status text
    - details: Detailed status description
    - success: Boolean indicating if check succeeded
    - error: Error message (if success=False)
    - incident_metadata: List of dicts with incident details
    - maintenance_metadata: List of dicts with maintenance details
    - components: List of component status dictionaries
"""
import requests
from bs4 import BeautifulSoup
import time
import logging
from typing import Dict, Any, List
import re

# Try to import Selenium for JavaScript rendering
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        WEBDRIVER_MANAGER_AVAILABLE = True
    except ImportError:
        WEBDRIVER_MANAGER_AVAILABLE = False
except ImportError:
    SELENIUM_AVAILABLE = False
    WEBDRIVER_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)

def fetch_rendered_html(url: str, timeout: int = 30) -> str:
    """
    Fetch HTML after JavaScript has rendered using Selenium.
    
    Args:
        url: URL to fetch
        timeout: Maximum time to wait for page to load
        
    Returns:
        Rendered HTML as string
        
    Raises:
        ImportError: If Selenium is not available
    """
    if not SELENIUM_AVAILABLE:
        raise ImportError("Selenium is required for JavaScript rendering. Install with: pip install selenium")
    
    logger.debug("Using Selenium to render JavaScript...")
    
    # Set up Chrome options for headless mode
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # Initialize driver
    try:
        if WEBDRIVER_MANAGER_AVAILABLE:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        logger.error(f"Failed to initialize ChromeDriver: {e}")
        logger.error("Make sure ChromeDriver is installed and in PATH, or install webdriver-manager")
        raise
    
    try:
        driver.get(url)
        
        # Wait for the page to load and JavaScript to render
        # We need to wait for:
        # 1. Skeleton loaders to disappear (or accordion items to be enabled)
        # 2. Multiple component accordion items to be present with actual content
        logger.debug("Page loaded, waiting for content to render...")
        
        try:
            # Wait for skeleton loaders to disappear or accordion items to be enabled
            # The page shows skeleton loaders initially, then loads actual component data
            wait = WebDriverWait(driver, timeout)
            
            # Wait for at least one accordion item that is NOT disabled and has actual content
            # Component accordion items have class "MuiAccordionSummary-root" and should not be disabled
            def component_content_loaded(driver):
                # Check for accordion items with actual component names (not skeleton loaders)
                accordion_items = driver.find_elements(By.CSS_SELECTOR, ".MuiAccordionSummary-root")
                if not accordion_items:
                    return False
                
                # Count enabled accordion items with actual component names
                enabled_with_content = 0
                for item in accordion_items:
                    # Skip if disabled
                    if item.get_attribute("aria-disabled") == "true":
                        continue
                    item_class = item.get_attribute("class") or ""
                    if "Mui-disabled" in item_class:
                        continue
                    
                    # Check if it has actual component name (not empty or skeleton)
                    text = item.text.strip()
                    if text and text not in ["", "Sign in"] and not text.startswith("Past"):
                        # Check if it's not a skeleton loader
                        skeleton = item.find_elements(By.CSS_SELECTOR, ".MuiSkeleton-root")
                        if not skeleton:
                            enabled_with_content += 1
                
                # We need at least 5 component items to be loaded (there are usually 20+ components)
                return enabled_with_content >= 5
            
            wait.until(component_content_loaded)
            logger.debug("Component content loaded successfully")
            
            # Additional small wait to ensure all components are fully rendered
            time.sleep(2)
            
        except Exception as e:
            logger.warning(f"Timeout waiting for component content to load: {e}, but continuing...")
            # Fallback: wait a bit longer and hope content loads
            time.sleep(5)
        
        html = driver.page_source
        logger.debug(f"Retrieved rendered HTML ({len(html)} characters)")
        
        return html
    finally:
        driver.quit()

def extract_component_statuses(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extract individual component statuses from the Outreach status page.
    
    Args:
        soup: BeautifulSoup parsed HTML
        
    Returns:
        List of dictionaries with component name and status
    """
    components = []
    
    # Look for MUI Typography elements (h6 with MuiTypography classes)
    mui_typography_elements = soup.find_all(['h6', 'h5', 'h4', 'div', 'span'], 
                                           class_=re.compile(r'MuiTypography|mui-', re.I))
    
    logger.debug(f"Found {len(mui_typography_elements)} MUI Typography elements")
    
    # Try to find component names and their associated status
    for elem in mui_typography_elements:
        component_name = elem.get_text(strip=True)
        skip_texts = ['status', 'operational', 'incident', 'maintenance', 'activity', 
                     'outreach', 'components', 'services', 'all systems', 'past incidents',
                     'about this site']
        
        # Filter out date-like strings (timestamps from past incidents)
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',
            r'\d{1,2}\s+pm\s+edt',
            r'\d{1,2}\s+am\s+edt',
            r'\d{1,2}:\d{2}\s+(am|pm)',
            r'\d{1,2}:\d{2}\s+(am|pm)\s+edt',
        ]
        
        is_date_like = any(re.search(pattern, component_name.lower()) for pattern in date_patterns)
        
        # Check if element is in a history/past/timeline section
        parent = elem.parent
        parent_classes = ''
        if parent:
            parent_classes = ' '.join(parent.get('class', []) + 
                                     (parent.parent.get('class', []) if parent.parent else []))
        
        is_in_history_section = any(keyword in parent_classes.lower() for keyword in 
                                   ['history', 'past', 'archive', 'timeline', 'incident'])
        
        # Only process if it looks like a component name
        if (component_name and 
            len(component_name) > 1 and 
            len(component_name) < 50 and
            component_name.lower() not in skip_texts and
            not component_name.isdigit() and
            not is_date_like and
            not is_in_history_section):
            
            parent = elem.parent
            status = 'unknown'
            
            # Strategy 1: Look for status in parent container
            if parent:
                parent_text = parent.get_text().lower()
                
                status_elem = parent.find(['span', 'div', 'p', 'svg'], 
                                         class_=re.compile(r'status|indicator|badge|operational|degraded|down', re.I))
                if status_elem:
                    status_text = status_elem.get_text(strip=True).lower()
                    if 'operational' in status_text or 'healthy' in status_text or 'up' in status_text:
                        status = 'operational'
                    elif 'degraded' in status_text or 'degradation' in status_text or 'partial' in status_text:
                        status = 'degraded'
                    elif 'down' in status_text or 'outage' in status_text or 'offline' in status_text:
                        status = 'down'
                    elif 'maintenance' in status_text:
                        status = 'maintenance'
                
                # Strategy 2: Check parent text content for status keywords
                if status == 'unknown':
                    if 'operational' in parent_text or 'all systems operational' in parent_text:
                        status = 'operational'
                    elif 'degraded' in parent_text or 'degradation' in parent_text:
                        status = 'degraded'
                    elif 'down' in parent_text or 'outage' in parent_text:
                        status = 'down'
                    elif 'maintenance' in parent_text:
                        status = 'maintenance'
            
            # Strategy 3: Check siblings
            if status == 'unknown':
                next_sib = elem.next_sibling
                while next_sib and status == 'unknown':
                    if hasattr(next_sib, 'get_text'):
                        next_text = next_sib.get_text().lower()
                        if 'operational' in next_text:
                            status = 'operational'
                        elif 'degraded' in next_text:
                            status = 'degraded'
                        elif 'down' in next_text or 'outage' in next_text:
                            status = 'down'
                        elif 'maintenance' in next_text:
                            status = 'maintenance'
                    next_sib = next_sib.next_sibling if hasattr(next_sib, 'next_sibling') else None
            
            # Strategy 4: Look for status in nearby elements
            if status == 'unknown' and parent:
                all_text = parent.get_text(' ', strip=True).lower()
                if 'operational' in all_text and component_name.lower() in all_text:
                    status = 'operational'
                elif 'degraded' in all_text and component_name.lower() in all_text:
                    status = 'degraded'
                elif ('down' in all_text or 'outage' in all_text) and component_name.lower() in all_text:
                    status = 'down'
            
            # Strategy 5: Check data attributes
            status_attr = (elem.get('aria-label') or 
                          elem.get('data-status') or 
                          (elem.parent and elem.parent.get('data-status')))
            if status_attr and status == 'unknown':
                status_text = status_attr.lower()
                if 'operational' in status_text:
                    status = 'operational'
                elif 'degraded' in status_text:
                    status = 'degraded'
                elif 'down' in status_text or 'outage' in status_text:
                    status = 'down'
                elif 'maintenance' in status_text:
                    status = 'maintenance'
            
            # Only add if we found a valid status or if it's a known component name pattern
            if component_name and (status != 'unknown' or component_name in ['Activity', 'Apps', 'Context', 'API', 'Web', 'Mobile']):
                if status == 'unknown':
                    status = 'operational'  # Default assumption
                
                components.append({
                    'name': component_name,
                    'status': status
                })
                logger.debug(f"Found component: {component_name} - {status}")
    
    # Remove duplicates and merge components with status suffixes
    normalized_components = {}
    status_suffixes = ['operational', 'degraded', 'down', 'maintenance', 'outage']
    
    for comp in components:
        name = comp['name']
        status = comp['status']
        
        # Check if name ends with a status suffix
        normalized_name = name
        for suffix in status_suffixes:
            if name.lower().endswith(suffix.lower()):
                normalized_name = name[:-len(suffix)].rstrip()
                break
        
        # Use normalized name as key
        if normalized_name in normalized_components:
            existing = normalized_components[normalized_name]
            if len(name) < len(existing['name']) or not any(suffix in name.lower() for suffix in status_suffixes):
                normalized_components[normalized_name] = {
                    'name': normalized_name if normalized_name != name else name,
                    'status': status
                }
        else:
            normalized_components[normalized_name] = {
                'name': normalized_name if normalized_name != name else name,
                'status': status
            }
    
    # Convert back to list
    unique_components = list(normalized_components.values())
    
    # Final deduplication pass
    seen = set()
    final_components = []
    for comp in unique_components:
        if comp['name'] not in seen:
            seen.add(comp['name'])
            final_components.append(comp)
    
    logger.info(f"Extracted {len(final_components)} component(s) after deduplication")
    return final_components

def check_outreach_status(url: str = "https://status.outreach.io/") -> Dict[str, Any]:
    """
    Check Outreach status page and parse HTML to extract status information.
    
    Args:
        url: URL of the Outreach status page
        
    Returns:
        Dictionary with status information
    """
    try:
        logger.info(f"Fetching Outreach status page: {url}")
        
        start_time = time.time()
        
        # Try to use Selenium for JavaScript rendering first
        use_selenium = True
        if SELENIUM_AVAILABLE:
            try:
                html_content = fetch_rendered_html(url)
                response_time = time.time() - start_time
                logger.info(f"Fetched and rendered page in {response_time:.2f}s using Selenium")
            except Exception as e:
                logger.warning(f"Selenium rendering failed: {e}, falling back to simple HTML fetch")
                use_selenium = False
                response = requests.get(
                    url,
                    timeout=15,
                    headers={'User-Agent': 'OutreachMonitor/1.0'}
                )
                response.raise_for_status()
                html_content = response.text
                response_time = time.time() - start_time
                logger.info(f"Fetched page in {response_time:.2f}s (no JavaScript rendering)")
        else:
            use_selenium = False
            logger.warning("Selenium not available. Install with: pip install selenium webdriver-manager")
            logger.warning("Attempting to parse static HTML (may miss JavaScript-rendered content)...")
            response = requests.get(
                url,
                timeout=15,
                headers={'User-Agent': 'OutreachMonitor/1.0'}
            )
            response.raise_for_status()
            html_content = response.text
            response_time = time.time() - start_time
            logger.info(f"Fetched page in {response_time:.2f}s")
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract component statuses first
        components = extract_component_statuses(soup)
        
        # Extract status information
        status_value = 1  # Default to operational
        raw_status = 'operational'
        status_text = 'Operational'
        details = 'All systems operational'
        incident_metadata = []
        maintenance_metadata = []
        
        # Look for status update sections
        update_sections = soup.find_all(['div', 'article', 'section'],
                                       class_=re.compile(r'update|incident|event|timeline|status', re.I))
        
        # Extract incident information - ONLY ACTIVE incidents
        incidents = []
        resolved_keywords = ['resolved', 'closed', 'completed', 'fixed', 'ended', 'postmortem', 'archived']
        active_keywords = ['investigating', 'monitoring', 'active', 'ongoing', 'open']
        
        for section in update_sections:
            text = section.get_text().lower()
            
            # Skip if this section contains resolved/closed keywords
            if any(keyword in text for keyword in resolved_keywords):
                logger.debug(f"Skipping resolved incident section: {section.get_text()[:100]}")
                continue
            
            # Only process if it contains incident keywords AND indicates it's active
            if any(keyword in text for keyword in ['incident', 'outage', 'degraded']):
                status_elem = section.find(['span', 'div', 'p'], 
                                         class_=re.compile(r'status|badge|indicator', re.I))
                status_text_elem = status_elem.get_text(strip=True).lower() if status_elem else ''
                
                # Check if status indicates resolved/closed
                if status_text_elem and any(keyword in status_text_elem for keyword in resolved_keywords):
                    logger.debug(f"Skipping resolved incident based on status: {status_text_elem}")
                    continue
                
                # Check if status indicates active
                is_active = False
                if any(keyword in text for keyword in active_keywords):
                    is_active = True
                elif status_text_elem and any(keyword in status_text_elem for keyword in active_keywords):
                    is_active = True
                elif not status_text_elem:
                    parent_classes = ' '.join(section.get('class', []) + 
                                            (section.parent.get('class', []) if section.parent else []))
                    if 'history' in parent_classes.lower() or 'past' in parent_classes.lower() or 'archive' in parent_classes.lower():
                        logger.debug(f"Skipping incident from history/past section")
                        continue
                    is_active = True
                
                if not is_active:
                    logger.debug(f"Skipping non-active incident section")
                    continue
                
                # Extract incident details
                title_elem = section.find(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
                title = title_elem.get_text(strip=True) if title_elem else 'Incident'
                
                time_elem = section.find(['time', 'span'], class_=re.compile(r'time|date', re.I))
                timestamp = time_elem.get('datetime') or time_elem.get_text(strip=True) if time_elem else ''
                
                desc_elem = section.find(['p', 'div'], class_=re.compile(r'description|content|message', re.I))
                description = desc_elem.get_text(strip=True) if desc_elem else ''
                
                severity_elem = section.find(['span', 'div'], class_=re.compile(r'severity|impact|status', re.I))
                severity = severity_elem.get_text(strip=True).lower() if severity_elem else 'unknown'
                
                impact = 'minor'
                if 'critical' in severity or 'major' in severity:
                    impact = severity
                elif 'minor' in severity:
                    impact = 'minor'
                
                incidents.append({
                    'title': title,
                    'description': description,
                    'timestamp': timestamp,
                    'severity': severity,
                    'impact': impact
                })
                logger.debug(f"Found ACTIVE incident: {title}")
        
        # Extract maintenance information
        maintenances = []
        for section in update_sections:
            text = section.get_text().lower()
            if any(keyword in text for keyword in ['maintenance', 'scheduled', 'upgrade']):
                title_elem = section.find(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
                title = title_elem.get_text(strip=True) if title_elem else 'Maintenance'
                
                time_elem = section.find(['time', 'span'], class_=re.compile(r'time|date', re.I))
                timestamp = time_elem.get('datetime') or time_elem.get_text(strip=True) if time_elem else ''
                
                desc_elem = section.find(['p', 'div'], class_=re.compile(r'description|content|message', re.I))
                description = desc_elem.get_text(strip=True) if desc_elem else ''
                
                maintenances.append({
                    'title': title,
                    'description': description,
                    'timestamp': timestamp
                })
        
        # Filter out resolved incidents
        active_incidents = []
        for inc in incidents:
            inc_text = (inc.get('title', '') + ' ' + inc.get('description', '')).lower()
            if not any(keyword in inc_text for keyword in resolved_keywords):
                active_incidents.append(inc)
            else:
                logger.debug(f"Filtered out resolved incident: {inc.get('title', 'Unknown')}")
        
        incidents = active_incidents
        
        # Update status based on component statuses
        non_operational_components = [c for c in components if c['status'] not in ['operational', 'unknown']]
        
        # Determine overall status
        if incidents:
            status_value = -1  # Incident
            severities = [inc.get('impact', 'minor') for inc in incidents]
            if 'critical' in severities:
                raw_status = 'critical'
                status_text = 'Critical Outage'
            elif 'major' in severities:
                raw_status = 'major'
                status_text = 'Major Outage'
            else:
                raw_status = 'minor'
                status_text = 'Minor Outage'
            
            incident_details = []
            for inc in incidents:
                detail = f"{inc.get('title', 'Incident')}"
                if inc.get('description'):
                    detail += f": {inc.get('description', '')[:100]}"
                incident_details.append(detail)
            details = '; '.join(incident_details)
            
            # Build incident metadata
            for idx, inc in enumerate(incidents):
                incident_metadata.append({
                    'id': f"outreach-incident-{idx+1}",
                    'name': inc.get('title', 'Incident'),
                    'status': 'investigating',
                    'impact': inc.get('impact', 'minor'),
                    'started_at': inc.get('timestamp', ''),
                    'updated_at': inc.get('timestamp', ''),
                    'shortlink': '',
                    'affected_components': []
                })
            logger.info(f"Found {len(incident_metadata)} active incident(s)")
        elif non_operational_components:
            status_value = -1
            raw_status = 'degraded'
            status_text = 'Degraded'
            component_names = [c['name'] for c in non_operational_components]
            details = f"Non-operational components: {', '.join(component_names)}"
            logger.warning(f"Found {len(non_operational_components)} non-operational component(s)")
        elif maintenances:
            status_value = 0  # Maintenance
            raw_status = 'maintenance'
            status_text = 'Maintenance'
            maint_details = [m.get('title', 'Maintenance') for m in maintenances]
            details = '; '.join(maint_details)
            
            # Build maintenance metadata
            for idx, maint in enumerate(maintenances):
                maintenance_metadata.append({
                    'id': f"outreach-maintenance-{idx+1}",
                    'name': maint.get('title', 'Maintenance'),
                    'status': 'scheduled',
                    'scheduled_start': maint.get('timestamp', ''),
                    'scheduled_end': '',
                    'shortlink': '',
                    'affected_components': []
                })
        
        logger.info(f"Parsed status: {status_text} ({raw_status})")
        logger.info(f"Found {len(incidents)} incident(s), {len(maintenances)} maintenance event(s)")
        
        return {
            'status': status_value,
            'response_time': response_time,
            'raw_status': raw_status,
            'status_text': status_text,
            'details': details,
            'success': True,
            'incident_metadata': incident_metadata,
            'maintenance_metadata': maintenance_metadata,
            'components': components,
            'javascript_rendered': use_selenium
        }
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 0
        logger.error(f"HTTP error: {status_code} - {e}")
        return {
            'status': None,
            'response_time': 0,
            'raw_status': f'http_{status_code}_error',
            'status_text': 'HTTP Error',
            'details': f"HTTP {status_code}: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'components': []
        }
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error: {e}")
        return {
            'status': None,
            'response_time': 0,
            'raw_status': 'timeout',
            'status_text': 'Timeout',
            'details': f"Request timeout: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'components': []
        }
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return {
            'status': None,
            'response_time': 0,
            'raw_status': 'connection_error',
            'status_text': 'Connection Error',
            'details': f"Connection failed: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'components': []
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'status': None,
            'response_time': 0,
            'raw_status': 'parse_error',
            'status_text': 'Parse Error',
            'details': f"Error parsing HTML: {str(e)}",
            'success': False,
            'error': str(e),
            'incident_metadata': [],
            'maintenance_metadata': [],
            'components': []
        }

