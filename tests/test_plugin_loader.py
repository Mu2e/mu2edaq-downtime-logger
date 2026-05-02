import pytest

from downtime_logger.core.plugin_loader import instantiate, load_class
from downtime_logger.core.metric import WeightedRatioMetric


def test_load_class_returns_class():
    cls = load_class("downtime_logger.core.metric:WeightedRatioMetric")
    assert cls is WeightedRatioMetric


def test_instantiate_passes_kwargs():
    obj = instantiate(
        "downtime_logger.core.metric:WeightedRatioMetric",
        trip_threshold=0.7,
        clear_threshold=0.1,
    )
    assert isinstance(obj, WeightedRatioMetric)
    assert obj.trip_threshold == 0.7
    assert obj.clear_threshold == 0.1


def test_bad_spec_format():
    with pytest.raises(ValueError):
        load_class("not_a_valid_spec")


def test_unknown_attribute():
    with pytest.raises(ImportError):
        load_class("downtime_logger.core.metric:DoesNotExist")
