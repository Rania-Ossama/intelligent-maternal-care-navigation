"""Loads config.yaml and resolves file paths."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """Thin wrapper around the parsed YAML with resolved paths."""

    def __init__(self, raw: dict[str, Any], base_dir: Path, config_path: Path):
        self.raw = raw
        self.base_dir = base_dir
        self.config_path = config_path

        p = raw["paths"]
        self.nodes_path = self._resolve(p["nodes"])
        self.edges_path = self._resolve(p["edges"])
        self.facilities_path = self._resolve(p["facilities"])
        self.processed_dir = self._resolve(p["processed_dir"])
        self.governorates_path = self._resolve(p.get("governorates", "boundaries_data/processed/egypt_governorates.geojson"))

        self.cols = raw["columns"]
        self.graph = raw["graph"]
        self.fac = raw["facilities"]
        self.search = raw["search"]
        self.server = raw["server"]
        self.map = raw["map"]
        self.gov = raw.get("governorates") or {}

        # processed files (created by the app)
        self.proc_nodes = self.processed_dir / "graph_nodes.parquet"
        self.proc_edges = self.processed_dir / "graph_edges.parquet"
        self.proc_meta = self.processed_dir / "graph_meta.json"
        self.proc_stitches = self.processed_dir / "stitched_edges.csv"
        self.proc_dropped = self.processed_dir / "dropped_pieces.csv"

    def _resolve(self, value: str) -> Path:
        path = Path(os.path.expandvars(os.path.expanduser(str(value))))
        if not path.is_absolute():
            path = self.base_dir / path
        return path

    def build_signature(self) -> str:
        """Hash of everything that changes how the processed graph is built."""
        payload = {
            "graph": self.graph,
            "cols_nodes": self.cols["nodes"],
            "cols_edges": self.cols["edges"],
            "version": 4,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha1(blob).hexdigest()[:16]


def load_settings(config_path: str | os.PathLike | None = None) -> Settings:
    path = Path(config_path or os.environ.get("HF_CONFIG") or PROJECT_ROOT / "config.yaml")
    path = path.resolve()
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml is not valid YAML: {exc}") from exc

    # Fill any missing sections from the defaults that ship with the app
    default_path = PROJECT_ROOT / "config.yaml"
    if default_path.exists() and default_path != path:
        with open(default_path, "r", encoding="utf-8") as fh:
            raw = _deep_merge(yaml.safe_load(fh) or {}, raw)

    for section in ("paths", "columns", "graph", "facilities", "search", "server", "map"):
        if section not in raw:
            raise ConfigError(f"config.yaml is missing the '{section}:' section")
    return Settings(raw, path.parent, path)
