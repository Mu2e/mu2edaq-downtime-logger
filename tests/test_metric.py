from datetime import datetime, timezone

from downtime_logger.core.event import DetectorReading, DetectorState
from downtime_logger.core.metric import WeightedRatioMetric


def _r(did: str, state: DetectorState, weight: float) -> DetectorReading:
    return DetectorReading(
        detector_id=did, state=state, weight=weight,
        ts=datetime.now(timezone.utc),
    )


def test_all_up_gives_zero_score_and_clear():
    m = WeightedRatioMetric(trip_threshold=0.6, clear_threshold=0.2)
    readings = {
        "a": _r("a", DetectorState.UP, 0.5),
        "b": _r("b", DetectorState.UP, 0.3),
    }
    score, is_down = m.evaluate(readings, previously_down=False)
    assert score == 0.0
    assert is_down is False


def test_all_down_gives_score_one_and_trips():
    m = WeightedRatioMetric()
    readings = {
        "a": _r("a", DetectorState.DOWN, 0.5),
        "b": _r("b", DetectorState.DOWN, 0.3),
    }
    score, is_down = m.evaluate(readings, previously_down=False)
    assert score == 1.0
    assert is_down is True


def test_weighted_ratio_at_trip_threshold():
    m = WeightedRatioMetric(trip_threshold=0.6, clear_threshold=0.2)
    readings = {
        "a": _r("a", DetectorState.DOWN, 0.6),
        "b": _r("b", DetectorState.UP, 0.4),
    }
    score, is_down = m.evaluate(readings, previously_down=False)
    assert abs(score - 0.6) < 1e-9
    assert is_down is True


def test_unknown_excluded_from_denominator():
    m = WeightedRatioMetric(trip_threshold=0.6, clear_threshold=0.2)
    readings = {
        "a": _r("a", DetectorState.DOWN, 1.0),
        "b": _r("b", DetectorState.UNKNOWN, 1.0),  # ignored
    }
    score, is_down = m.evaluate(readings, previously_down=False)
    assert score == 1.0
    assert is_down is True


def test_hysteresis_blocks_premature_clear():
    m = WeightedRatioMetric(trip_threshold=0.6, clear_threshold=0.2)
    # Already down. Score 0.4 is below trip but above clear -> stay down.
    readings = {
        "a": _r("a", DetectorState.DOWN, 0.4),
        "b": _r("b", DetectorState.UP, 0.6),
    }
    score, is_down = m.evaluate(readings, previously_down=True)
    assert abs(score - 0.4) < 1e-9
    assert is_down is True


def test_hysteresis_clears_below_clear_threshold():
    m = WeightedRatioMetric(trip_threshold=0.6, clear_threshold=0.2)
    readings = {
        "a": _r("a", DetectorState.DOWN, 0.1),
        "b": _r("b", DetectorState.UP, 0.9),
    }
    score, is_down = m.evaluate(readings, previously_down=True)
    assert abs(score - 0.1) < 1e-9
    assert is_down is False


def test_no_known_readings_gives_zero():
    m = WeightedRatioMetric()
    readings = {"a": _r("a", DetectorState.UNKNOWN, 1.0)}
    score, is_down = m.evaluate(readings, previously_down=False)
    assert score == 0.0
    assert is_down is False
