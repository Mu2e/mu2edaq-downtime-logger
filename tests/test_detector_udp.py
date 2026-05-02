"""
End-to-end test for UdpDetector against a real localhost UDP socket. The
detector lives on the main thread under qtbot, so signals are observable
without spinning up an extra QThread.
"""
import socket
import time

import pytest

from downtime_logger.core.event import DetectorState
from downtime_logger.detectors.udp_detector import UdpDetector


def _free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def detector(qtbot):
    port = _free_udp_port()
    det = UdpDetector(
        detector_id="udp",
        bind="127.0.0.1",
        port=port,
        heartbeat_timeout_s=999,
    )
    det.start()
    yield det, port
    det.stop()


def test_udp_running_message_emits_up(qtbot, detector):
    det, port = detector
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with qtbot.waitSignal(det.state_changed, timeout=2000) as blocker:
        sock.sendto(b"DAQ STATE running", ("127.0.0.1", port))
    assert blocker.args[1] == DetectorState.UP.value


def test_udp_stopped_message_emits_down(qtbot, detector):
    det, port = detector
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with qtbot.waitSignal(det.state_changed, timeout=2000) as blocker:
        sock.sendto(b"DAQ STATE stopped", ("127.0.0.1", port))
    assert blocker.args[1] == DetectorState.DOWN.value


def test_udp_heartbeat_timeout_emits_down(qtbot):
    port = _free_udp_port()
    det = UdpDetector(
        detector_id="udp",
        bind="127.0.0.1",
        port=port,
        heartbeat_timeout_s=0.05,
    )
    try:
        with qtbot.waitSignal(det.state_changed, timeout=2000) as blocker:
            det.start()
            time.sleep(0.01)  # let timer arm
        assert blocker.args[1] == DetectorState.DOWN.value
    finally:
        det.stop()
