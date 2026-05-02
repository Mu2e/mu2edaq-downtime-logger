import os
import time

from downtime_logger.core.event import DetectorState
from downtime_logger.detectors.disk_detector import DiskActivityDetector


def test_disk_idle_trips_down(tmp_path):
    det = DiskActivityDetector(
        detector_id="d",
        paths=[str(tmp_path)],
        idle_seconds=0.1,
        poll_s=999,  # we drive _tick by hand
    )
    seen: list[str] = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    # Force a stale last-event timestamp.
    det._last_event_ts = time.time() - 10
    det._tick()
    assert seen[-1] == DetectorState.DOWN.value


def test_disk_recent_write_keeps_up(tmp_path):
    det = DiskActivityDetector(
        detector_id="d",
        paths=[str(tmp_path)],
        idle_seconds=60,
        poll_s=999,
    )
    seen: list[str] = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._last_event_ts = time.time()
    det._tick()
    assert seen[-1] == DetectorState.UP.value


def test_seed_picks_up_existing_mtime(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"x")
    older = time.time() - 5
    os.utime(f, (older, older))
    latest = DiskActivityDetector._scan_latest_mtime([str(tmp_path)])
    assert latest is not None
    assert abs(latest - older) < 1.0
