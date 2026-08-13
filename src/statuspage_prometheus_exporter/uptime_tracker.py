"""
Uptime/SLA History Tracking Module

This module maintains a rolling history of each service's operational status
(one sample per monitoring run) and computes uptime percentages over fixed
rolling windows, for the statuspage_uptime_percentage gauge.

Storage:
    - Each service has its own JSON Lines history file: cache/{service_key}_uptime.jsonl
    - One line per monitoring run: {"ts": "<ISO 8601 UTC timestamp>", "status": 0 or 1}
    - A sample is only recorded when a service's status is known for that run
      (a live check or cache-fallback result) - a check that failed with no
      cached data available records nothing, rather than counting as downtime
    - History is trimmed to the longest configured window on every write, so
      file size stays bounded regardless of how long the exporter has been running

Rolling Windows:
    - 24h, 7d, 30d - percentage of recorded samples with status == 1 (operational)
    - A window with no samples yet (e.g. a newly added service) is omitted from
      the result rather than reported as 0% or 100%

Like the response cache in cache_manager.py, this history lives in the 'cache'
directory - mount it to persistent storage in Kubernetes/Docker so uptime
percentages survive pod/container restarts instead of resetting to "no data".
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .cache_manager import get_cache_directory, ensure_cache_directory

logger = logging.getLogger(__name__)

# Rolling windows (label -> hours) exposed as the statuspage_uptime_percentage
# "window" label value.
WINDOWS: Dict[str, int] = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}

# History is trimmed to the longest window on every write.
_MAX_RETENTION_HOURS = max(WINDOWS.values())


def get_history_path(service_key: str) -> Path:
    """
    Get the uptime history file path for a service.

    Args:
        service_key: Service identifier key

    Returns:
        Path object pointing to the history file
    """
    cache_dir = ensure_cache_directory()
    return cache_dir / f"{service_key}_uptime.jsonl"


def _parse_timestamp(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _read_samples(service_key: str) -> List[dict]:
    """Read all valid samples from a service's history file, skipping bad lines."""
    history_path = get_history_path(service_key)
    if not history_path.exists():
        return []

    samples = []
    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if _parse_timestamp(entry.get("ts", "")) is not None and entry.get(
                    "status"
                ) in (0, 1):
                    samples.append(entry)
                else:
                    logger.warning(
                        f"Skipping malformed uptime history entry for {service_key}: {line}"
                    )
            except json.JSONDecodeError:
                logger.warning(
                    f"Skipping unparseable uptime history line for {service_key}: {line}"
                )
    return samples


def _write_samples(service_key: str, samples: List[dict]) -> None:
    """Atomically overwrite a service's history file with the given samples."""
    history_path = get_history_path(service_key)
    temp_file = history_path.with_suffix(".jsonl.tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        for entry in samples:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
    temp_file.replace(history_path)


def append_status_sample(
    service_key: str, status_value: int, timestamp: Optional[datetime] = None
) -> bool:
    """
    Record one status sample for a service and trim history older than the
    longest configured window.

    Args:
        service_key: Service identifier key
        status_value: 1 (operational) or 0 (incident/down)
        timestamp: Sample time (defaults to now, UTC)

    Returns:
        True if the write succeeded, False otherwise
    """
    try:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        cutoff = timestamp - timedelta(hours=_MAX_RETENTION_HOURS)

        # _read_samples only returns entries with a parseable "ts", so this
        # comparison is always against a valid datetime.
        samples = [
            s for s in _read_samples(service_key) if _parse_timestamp(s["ts"]) >= cutoff
        ]
        samples.append({"ts": timestamp.isoformat(), "status": int(status_value)})

        _write_samples(service_key, samples)
        return True

    except Exception as e:
        logger.error(f"Failed to record uptime sample for {service_key}: {e}")
        return False


def compute_uptime_percentages(
    service_key: str, now: Optional[datetime] = None
) -> Dict[str, Optional[float]]:
    """
    Compute the uptime percentage for a service over each configured rolling window.

    Args:
        service_key: Service identifier key
        now: Reference time for the windows (defaults to now, UTC)

    Returns:
        Dict of window label -> percentage (0-100), or None for a window with
        no recorded samples yet
    """
    if now is None:
        now = datetime.now(timezone.utc)

    samples = _read_samples(service_key)
    result: Dict[str, Optional[float]] = {}
    for label, hours in WINDOWS.items():
        cutoff = now - timedelta(hours=hours)
        window_samples = [
            s for s in samples if (_parse_timestamp(s["ts"]) or cutoff) >= cutoff
        ]
        if not window_samples:
            result[label] = None
        else:
            operational = sum(1 for s in window_samples if s["status"] == 1)
            result[label] = (operational / len(window_samples)) * 100

    return result


def clear_uptime_history(service_key: Optional[str] = None) -> bool:
    """
    Clear uptime history file(s), mirroring cache_manager.clear_cache.

    Args:
        service_key: If provided, clear only this service's history.
                    If None, clear all history files.

    Returns:
        True if the operation succeeded, False otherwise
    """
    try:
        if service_key:
            history_path = get_history_path(service_key)
            if history_path.exists():
                history_path.unlink()
                logger.info(f"Cleared uptime history for {service_key}")
            return True

        cache_dir = get_cache_directory()
        if cache_dir.exists():
            for history_path in cache_dir.glob("*_uptime.jsonl"):
                history_path.unlink()
            logger.info(f"Cleared all uptime history files in {cache_dir}")
        return True

    except Exception as e:
        logger.error(f"Failed to clear uptime history: {e}")
        return False
