"""
SoapDetector tests. The zeep client is patched out so we test only the
detector's response-parsing and state transitions.
"""
from types import SimpleNamespace
from unittest.mock import patch

from downtime_logger.core.event import DetectorState
from downtime_logger.detectors.soap_detector import SoapDetector, _dig


def test_dig_dotted_paths():
    obj = SimpleNamespace(
        result=SimpleNamespace(runState="Running", inner={"x": 1})
    )
    assert _dig(obj, "result.runState") == "Running"
    assert _dig(obj, "result.inner.x") == 1
    assert _dig(obj, "result.missing") is None


class _FakeService:
    def __init__(self, value):
        self.value = value

    def getRunState(self, **_):
        if isinstance(self.value, Exception):
            raise self.value
        return SimpleNamespace(runState=self.value)


class _FakeClient:
    def __init__(self, value):
        self.service = _FakeService(value)


def _make_detector(value, state_path="runState"):
    det = SoapDetector(
        detector_id="s",
        wsdl="http://x/wsdl",
        operation="getRunState",
        state_path=state_path,
        down_values=["Stopped", "Idle"],
        up_values=["Running"],
        poll_s=999,
    )
    det._client = _FakeClient(value)
    return det


def test_soap_running_emits_up():
    det = _make_detector("Running")
    seen: list = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._poll()
    assert seen[-1] == DetectorState.UP.value


def test_soap_stopped_emits_down():
    det = _make_detector("Stopped")
    seen: list = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._poll()
    assert seen[-1] == DetectorState.DOWN.value


def test_soap_unrecognized_value_emits_unknown():
    det = _make_detector("Configuring")
    seen: list = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._poll()
    assert seen[-1] == DetectorState.UNKNOWN.value


def test_soap_call_failure_emits_unknown_and_resets_client():
    det = _make_detector(RuntimeError("connection refused"))
    seen: list = []
    det.state_changed.connect(lambda did, st, detail: seen.append(st))
    det._poll()
    assert seen[-1] == DetectorState.UNKNOWN.value
    assert det._client is None  # forced re-init


def test_soap_wsdl_init_failure(monkeypatch):
    det = SoapDetector(
        detector_id="s", wsdl="http://x/wsdl", poll_s=999,
    )
    with patch("downtime_logger.detectors.soap_detector.Client",
               side_effect=RuntimeError("fetch failed")):
        seen: list = []
        det.state_changed.connect(lambda did, st, detail: seen.append(st))
        det._poll()
        assert seen[-1] == DetectorState.UNKNOWN.value
