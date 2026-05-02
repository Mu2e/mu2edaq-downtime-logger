"""
ZmqDetector against a localhost PUB socket.
"""
import time

import pytest
import zmq

from downtime_logger.core.event import DetectorState
from downtime_logger.detectors.zeromq_detector import ZmqDetector


@pytest.fixture
def pub_endpoint():
    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    port = pub.bind_to_random_port("tcp://127.0.0.1")
    endpoint = f"tcp://127.0.0.1:{port}"
    yield pub, endpoint
    pub.close(0)


def test_zmq_running_emits_up(qtbot, pub_endpoint):
    pub, endpoint = pub_endpoint
    det = ZmqDetector(detector_id="z", endpoint=endpoint, heartbeat_timeout_s=999)
    det.start()
    try:
        # Slow joiner: give SUB a moment to actually subscribe.
        time.sleep(0.2)
        with qtbot.waitSignal(det.state_changed, timeout=3000) as blocker:
            for _ in range(5):
                pub.send_string("RUN STATE running")
                qtbot.wait(50)
        assert blocker.args[1] == DetectorState.UP.value
    finally:
        det.stop()


def test_zmq_stopped_emits_down(qtbot, pub_endpoint):
    pub, endpoint = pub_endpoint
    det = ZmqDetector(detector_id="z", endpoint=endpoint, heartbeat_timeout_s=999)
    det.start()
    try:
        time.sleep(0.2)
        with qtbot.waitSignal(det.state_changed, timeout=3000) as blocker:
            for _ in range(5):
                pub.send_string("RUN STATE stopped")
                qtbot.wait(50)
        assert blocker.args[1] == DetectorState.DOWN.value
    finally:
        det.stop()
