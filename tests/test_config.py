import pytest
import yaml

from downtime_logger.config import AppConfig


VALID = {
    "storage": {
        "plugin": "downtime_logger.storage.sqlite_backend:SQLiteBackend",
        "options": {"path": "x.db"},
    },
    "metric": {
        "plugin": "downtime_logger.core.metric:WeightedRatioMetric",
        "options": {"trip_threshold": 0.6, "clear_threshold": 0.2},
    },
    "detectors": [
        {"id": "a", "plugin": "pkg.mod:A", "weight": 0.5, "options": {"x": 1}},
        {"id": "b", "plugin": "pkg.mod:B", "weight": 0.3},
    ],
}


def test_load_from_dict_ok():
    cfg = AppConfig.from_dict(VALID)
    assert cfg.storage.options["path"] == "x.db"
    assert cfg.metric.options["trip_threshold"] == 0.6
    assert [d.id for d in cfg.detectors] == ["a", "b"]
    assert cfg.detectors[1].weight == 0.3


def test_load_from_yaml_file(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(VALID))
    cfg = AppConfig.load(path)
    assert len(cfg.detectors) == 2


def test_missing_storage_section():
    bad = {k: v for k, v in VALID.items() if k != "storage"}
    with pytest.raises(ValueError):
        AppConfig.from_dict(bad)


def test_missing_detectors_rejected():
    bad = dict(VALID)
    bad["detectors"] = []
    with pytest.raises(ValueError):
        AppConfig.from_dict(bad)


def test_duplicate_detector_ids_rejected():
    bad = dict(VALID)
    bad["detectors"] = [
        {"id": "a", "plugin": "pkg.mod:A"},
        {"id": "a", "plugin": "pkg.mod:B"},
    ]
    with pytest.raises(ValueError):
        AppConfig.from_dict(bad)


def test_detector_missing_required_fields():
    bad = dict(VALID)
    bad["detectors"] = [{"plugin": "pkg.mod:A"}]  # no id
    with pytest.raises(ValueError):
        AppConfig.from_dict(bad)
