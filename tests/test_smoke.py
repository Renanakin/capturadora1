"""Smoke test del entry-point."""

from __future__ import annotations

from pathlib import Path

from ocr_tributario import __version__


def test_version_is_string():
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_settings_load(tmp_path: Path):
    """Carga settings y resuelve las rutas base."""
    from ocr_tributario.config.loader import load_settings
    settings = load_settings()
    assert settings.paths.input_dir
    assert settings.paths.output_dir
    assert settings.excel.template_columns  # al menos una columna