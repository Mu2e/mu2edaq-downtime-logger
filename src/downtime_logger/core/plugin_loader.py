"""
Tiny dynamic-import helper. ``module.path:ClassName`` -> instantiated object.

Kept deliberately minimal — entry-point machinery is overkill for an
in-tree plugin set, and ``importlib`` covers the "drop a file, name it
in YAML" use case cleanly.
"""
from __future__ import annotations

import importlib
from typing import Any


def load_class(spec: str) -> type:
    if ":" not in spec:
        raise ValueError(
            f"Plugin spec {spec!r} must be of the form 'module.path:ClassName'"
        )
    module_path, class_name = spec.split(":", 1)
    module = importlib.import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(
            f"Module {module_path!r} has no attribute {class_name!r}"
        ) from e


def instantiate(spec: str, **kwargs: Any) -> Any:
    cls = load_class(spec)
    return cls(**kwargs)
