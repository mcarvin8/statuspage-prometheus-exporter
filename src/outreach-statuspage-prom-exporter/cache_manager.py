"""
Cache Management Module for Service Response Data

This module provides functions to persist service response data to local JSON files
and retrieve cached responses when API requests fail. This prevents alerts from
clearing and re-firing when a single request fails during the 20-minute check interval.

Cache Strategy:
    - Service response is stored in JSON cache file: cache/outreach.json
    - Successful API responses are saved immediately to cache
    - Failed requests fall back to cached data (if available)
    - Cache files are stored in a 'cache' directory relative to the script

Functions:
    - save_service_response: Save successful response data to cache file
    - load_service_response: Load cached response data for the service
    - get_cache_path: Get the cache file path
    - ensure_cache_directory: Ensure the cache directory exists

Cache File Format:
    {
        "service_key": "outreach",
        "timestamp": "2025-01-15T10:30:00Z",
        "response_data": {
            // Full response dictionary from check_outreach_status
        }
    }
"""
import json
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

SERVICE_KEY = "outreach"

def get_cache_directory() -> Path:
    """
    Get the cache directory path.
    
    Returns:
        Path object pointing to the cache directory
    """
    # Cache directory is relative to this script's location
    script_dir = Path(__file__).parent
    cache_dir = script_dir / 'cache'
    return cache_dir

def ensure_cache_directory() -> Path:
    """
    Ensure the cache directory exists, creating it if necessary.
    
    Returns:
        Path object pointing to the cache directory
    """
    cache_dir = get_cache_directory()
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Cache directory ensured: {cache_dir}")
    return cache_dir

def get_cache_path() -> Path:
    """
    Get the cache file path for Outreach service.
    
    Returns:
        Path object pointing to the cache file
    """
    cache_dir = ensure_cache_directory()
    cache_file = cache_dir / f"{SERVICE_KEY}.json"
    return cache_file

def save_service_response(response_data: Dict[str, Any]) -> bool:
    """
    Save service response data to cache file.
    
    Args:
        response_data: Response dictionary from check_outreach_status
        
    Returns:
        True if save succeeded, False otherwise
    """
    try:
        cache_file = get_cache_path()
        
        cache_entry = {
            'service_key': SERVICE_KEY,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'response_data': response_data
        }
        
        # Write to temporary file first, then rename (atomic operation)
        temp_file = cache_file.with_suffix('.json.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cache_entry, f, indent=2, ensure_ascii=False)
        
        # Atomic rename (works on Unix and Windows)
        temp_file.replace(cache_file)
        
        logger.debug(f"Saved response cache for {SERVICE_KEY} to {cache_file}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save cache for {SERVICE_KEY}: {e}")
        return False

def load_service_response() -> Optional[Dict[str, Any]]:
    """
    Load cached service response data.
    
    Returns:
        Cached response data dictionary, or None if cache doesn't exist or is invalid
    """
    try:
        cache_file = get_cache_path()
        
        if not cache_file.exists():
            logger.debug(f"No cache file found for {SERVICE_KEY}")
            return None
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_entry = json.load(f)
        
        # Validate cache entry structure
        if 'response_data' not in cache_entry:
            logger.warning(f"Invalid cache entry for {SERVICE_KEY}: missing 'response_data'")
            return None
        
        response_data = cache_entry['response_data']
        timestamp = cache_entry.get('timestamp', 'unknown')
        
        logger.info(f"Loaded cached response for {SERVICE_KEY} (cached at {timestamp})")
        return response_data
        
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in cache file for {SERVICE_KEY}: {e}")
        # Try to remove corrupted cache file
        try:
            cache_file = get_cache_path()
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"Removed corrupted cache file for {SERVICE_KEY}")
        except Exception:
            pass
        return None
        
    except Exception as e:
        logger.warning(f"Failed to load cache for {SERVICE_KEY}: {e}")
        return None

def clear_cache() -> bool:
    """
    Clear cache file.
    
    Returns:
        True if operation succeeded, False otherwise
    """
    try:
        cache_file = get_cache_path()
        if cache_file.exists():
            cache_file.unlink()
            logger.info(f"Cleared cache for {SERVICE_KEY}")
        return True
            
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        return False

