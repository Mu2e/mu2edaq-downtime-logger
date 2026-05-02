"""
Pure-logic test for LogfileDetector — drives the tail loop directly with
synthetic file content. No QThread/QTimer is exercised here; the timer
just calls ``_tick`` on the same thread, which is exactly what the test
does explicitly.
"""
from downtime_logger.core.event import DetectorState
from downtime_logger.detectors.logfile_detector import LogfileDetector


def test_logfile_detector_flips_on_match(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("startup\n")

    det = LogfileDetector(
        detector_id="lg",
        path=str(log),
        down_patterns=["RUN STOPPED", "FATAL"],
        up_patterns=["RUN STARTED"],
    )

    seen: list[tuple[str, str]] = []
    det.state_changed.connect(lambda did, st, detail: seen.append((did, st)))

    # Prime the tail to current end-of-file.
    det._tick()
    assert seen == []

    with open(log, "a") as f:
        f.write("ts=12345 RUN STOPPED reason=hardware\n")
    det._tick()
    assert seen[-1] == ("lg", DetectorState.DOWN.value)

    with open(log, "a") as f:
        f.write("ts=12399 RUN STARTED ok\n")
    det._tick()
    assert seen[-1] == ("lg", DetectorState.UP.value)


def test_logfile_detector_no_match_no_emit(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("")
    det = LogfileDetector(
        detector_id="lg",
        path=str(log),
        down_patterns=["FATAL"],
        up_patterns=["READY"],
    )
    seen: list = []
    det.state_changed.connect(lambda *args: seen.append(args))
    det._tick()
    with open(log, "a") as f:
        f.write("nothing of interest\n")
    det._tick()
    assert seen == []


def test_logfile_detector_handles_rotation(tmp_path):
    log = tmp_path / "r.log"
    log.write_text("")
    det = LogfileDetector(
        detector_id="lg",
        path=str(log),
        down_patterns=["FATAL"],
        up_patterns=["READY"],
    )
    seen: list = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._tick()

    with open(log, "a") as f:
        f.write("FATAL boom\n")
    det._tick()
    assert seen[-1] == DetectorState.DOWN.value

    # Simulate logrotate: replace the file entirely.
    log.unlink()
    log.write_text("READY again\n")
    det._tick()
    assert seen[-1] == DetectorState.UP.value
