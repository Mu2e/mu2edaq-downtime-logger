"""
Metric module — isolated by design.

The combination logic that turns per-detector readings into a single
"is the DAQ down?" decision lives here and only here. To change the rule
(e.g. swap weighted-ratio for a Bayesian model, a quorum vote, a
neural-net scorer), implement a new ``Metric`` subclass and point at it
from YAML — no changes required in detectors, state machine, storage, or UI.

Contract:

    score, is_down = metric.evaluate(readings, previously_down)

* ``readings``: dict[detector_id -> DetectorReading]
* ``previously_down``: bool — current state-machine state, supplied so the
  metric can implement hysteresis (separate trip vs clear thresholds).
* ``score``: float in [0, 1] (or any range the metric defines; persisted as-is).
* ``is_down``: bool — what the state machine should treat as the new state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from .event import DetectorReading, DetectorState


class Metric(ABC):
    @abstractmethod
    def evaluate(
        self,
        readings: Mapping[str, DetectorReading],
        previously_down: bool,
    ) -> tuple[float, bool]:
        ...


@dataclass
class WeightedRatioMetric(Metric):
    """
    score = sum(weight where DOWN) / sum(weight where state in {UP, DOWN})

    Detectors reporting UNKNOWN are excluded from the denominator (they don't
    drag the score either direction). Hysteresis: once tripped, the score
    must fall below ``clear_threshold`` to recover.
    """

    trip_threshold: float = 0.6
    clear_threshold: float = 0.2

    def evaluate(
        self,
        readings: Mapping[str, DetectorReading],
        previously_down: bool,
    ) -> tuple[float, bool]:
        down_w = 0.0
        known_w = 0.0
        for r in readings.values():
            if r.state is DetectorState.UNKNOWN:
                continue
            known_w += r.weight
            if r.state is DetectorState.DOWN:
                down_w += r.weight

        score = (down_w / known_w) if known_w > 0 else 0.0

        if previously_down:
            is_down = score > self.clear_threshold
        else:
            is_down = score >= self.trip_threshold
        return score, is_down
