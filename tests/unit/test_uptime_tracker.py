from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture()
def history_dir(tmp_path):
    with patch(
        "statuspage_prometheus_exporter.uptime_tracker.ensure_cache_directory",
        return_value=tmp_path,
    ), patch(
        "statuspage_prometheus_exporter.uptime_tracker.get_cache_directory",
        return_value=tmp_path,
    ):
        yield tmp_path


def test_no_history_returns_none_for_all_windows(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import compute_uptime_percentages

    result = compute_uptime_percentages("svc")
    assert result == {"24h": None, "7d": None, "30d": None}


def test_append_and_compute_all_operational(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        compute_uptime_percentages,
    )

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    for i in range(5):
        append_status_sample("svc", 1, timestamp=now - timedelta(hours=i))

    result = compute_uptime_percentages("svc", now=now)
    assert result["24h"] == 100.0
    assert result["7d"] == 100.0
    assert result["30d"] == 100.0


def test_compute_mixed_status_percentage(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        compute_uptime_percentages,
    )

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    append_status_sample("svc", 1, timestamp=now)
    append_status_sample("svc", 1, timestamp=now - timedelta(hours=1))
    append_status_sample("svc", 0, timestamp=now - timedelta(hours=2))
    append_status_sample("svc", 1, timestamp=now - timedelta(hours=3))

    result = compute_uptime_percentages("svc", now=now)
    assert result["24h"] == 75.0


def test_samples_outside_window_excluded(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        compute_uptime_percentages,
    )

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    # Two samples within 24h (both up), one sample 10 days ago (down) - should
    # only affect the 30d window, not 24h/7d.
    append_status_sample("svc", 1, timestamp=now)
    append_status_sample("svc", 1, timestamp=now - timedelta(hours=1))
    append_status_sample("svc", 0, timestamp=now - timedelta(days=10))

    result = compute_uptime_percentages("svc", now=now)
    assert result["24h"] == 100.0
    assert result["7d"] == 100.0
    assert result["30d"] == pytest.approx(66.666, rel=1e-3)


def test_history_trimmed_beyond_max_retention(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        get_history_path,
    )

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    # Older than the 30d max retention window - should be dropped on next append.
    append_status_sample("svc", 0, timestamp=now - timedelta(days=45))
    append_status_sample("svc", 1, timestamp=now)

    lines = get_history_path("svc").read_text().strip().splitlines()
    assert len(lines) == 1


def test_malformed_lines_are_skipped(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        compute_uptime_percentages,
        get_history_path,
    )

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    append_status_sample("svc", 1, timestamp=now)

    history_path = get_history_path("svc")
    with open(history_path, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write("not valid json\n")
        f.write('{"ts": "not-a-timestamp", "status": 1}\n')
        f.write('{"ts": "2026-01-15T00:00:00+00:00", "status": "bad"}\n')

    result = compute_uptime_percentages("svc", now=now)
    assert result["24h"] == 100.0


def test_clear_uptime_history_specific_service(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        clear_uptime_history,
        get_history_path,
    )

    append_status_sample("svc_a", 1)
    append_status_sample("svc_b", 1)
    clear_uptime_history("svc_a")
    assert not get_history_path("svc_a").exists()
    assert get_history_path("svc_b").exists()


def test_clear_uptime_history_all(history_dir):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        clear_uptime_history,
        get_history_path,
    )

    append_status_sample("svc_a", 1)
    append_status_sample("svc_b", 0)
    clear_uptime_history()
    assert not get_history_path("svc_a").exists()
    assert not get_history_path("svc_b").exists()


def test_clear_uptime_history_noop_when_nothing_exists(tmp_path):
    from statuspage_prometheus_exporter.uptime_tracker import clear_uptime_history

    empty_dir = tmp_path / "does_not_exist"
    with patch(
        "statuspage_prometheus_exporter.uptime_tracker.get_cache_directory",
        return_value=empty_dir,
    ):
        assert clear_uptime_history() is True


def test_append_fails_gracefully_on_write_error(history_dir, monkeypatch):
    from statuspage_prometheus_exporter.uptime_tracker import append_status_sample

    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")),
    )
    assert append_status_sample("svc", 1) is False


def test_clear_uptime_history_fails_gracefully(history_dir, monkeypatch):
    from statuspage_prometheus_exporter.uptime_tracker import (
        append_status_sample,
        clear_uptime_history,
    )

    append_status_sample("svc", 1)

    def raise_error(*a, **kw):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.unlink", raise_error)
    assert clear_uptime_history("svc") is False
