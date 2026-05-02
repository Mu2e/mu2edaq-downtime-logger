from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PluginSpec:
    plugin: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectorSpec(PluginSpec):
    id: str = ""
    weight: float = 1.0


@dataclass
class WebServerSpec:
    enabled: bool = False
    bind: str = "0.0.0.0"
    port: int = 8088
    refresh_seconds: int = 5
    history_limit: int = 200


@dataclass
class AppConfig:
    storage: PluginSpec
    metric: PluginSpec
    detectors: list[DetectorSpec]
    webserver: WebServerSpec = field(default_factory=WebServerSpec)

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        try:
            storage = PluginSpec(
                plugin=raw["storage"]["plugin"],
                options=raw["storage"].get("options", {}) or {},
            )
            metric = PluginSpec(
                plugin=raw["metric"]["plugin"],
                options=raw["metric"].get("options", {}) or {},
            )
        except KeyError as e:
            raise ValueError(f"Missing required config section: {e}") from e

        detectors: list[DetectorSpec] = []
        for i, d in enumerate(raw.get("detectors", []) or []):
            if "id" not in d or "plugin" not in d:
                raise ValueError(f"detector[{i}] missing required 'id' or 'plugin'")
            detectors.append(
                DetectorSpec(
                    id=d["id"],
                    plugin=d["plugin"],
                    weight=float(d.get("weight", 1.0)),
                    options=d.get("options", {}) or {},
                )
            )
        if not detectors:
            raise ValueError("At least one detector must be configured")

        ids = [d.id for d in detectors]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate detector ids in config: {ids}")

        web_raw = raw.get("webserver", {}) or {}
        webserver = WebServerSpec(
            enabled=bool(web_raw.get("enabled", False)),
            bind=str(web_raw.get("bind", "0.0.0.0")),
            port=int(web_raw.get("port", 8088)),
            refresh_seconds=int(web_raw.get("refresh_seconds", 5)),
            history_limit=int(web_raw.get("history_limit", 200)),
        )

        return cls(
            storage=storage,
            metric=metric,
            detectors=detectors,
            webserver=webserver,
        )
