"""Carga de configuración: settings.yaml + .env (Fase 1)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ocr_tributario.config.schema import PathsConfig, Settings

# Raíz del proyecto (donde vive config/settings.yaml)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
ENV_FILE = PROJECT_ROOT / ".env"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _resolve_paths(data: dict) -> PathsConfig:
    paths_data = data.get("paths", {}) or {}
    env_overrides = {
        "input_dir": os.getenv("CAPTURADOR_INPUT_DIR"),
        "output_dir": os.getenv("CAPTURADOR_OUTPUT_DIR"),
        "quarantine_dir": os.getenv("CAPTURADOR_QUARANTINE_DIR"),
        "tesseract_cmd": os.getenv("TESSERACT_CMD"),
        "tessdata_prefix": os.getenv("TESSDATA_PREFIX"),
    }
    for key, val in env_overrides.items():
        if val:
            paths_data[key] = val
    return PathsConfig(**paths_data)


def _resolve_api(data: dict) -> dict:
    api_data = data.get("api", {}) or {}
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        api_data["redis_url"] = redis_url
    return api_data


@lru_cache(maxsize=1)
def load_settings(settings_path: Path | None = None) -> Settings:
    """Carga settings.yaml + .env. Cacheado en proceso."""
    load_dotenv(ENV_FILE, override=False)
    path = settings_path or DEFAULT_SETTINGS_PATH
    data = _load_yaml(path)
    
    api_config = _resolve_api(data)
    
    return Settings(
        paths=_resolve_paths(data),
        api=api_config,
        **{k: v for k, v in data.items() if k not in ("paths", "api")}
    )