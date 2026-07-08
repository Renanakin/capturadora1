"""Logging estructurado con loguru (Fase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONFIGURED = False


def setup_logging(verbose: bool = False, log_dir: Path | None = None) -> None:
    """Configura loguru una sola vez por proceso."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger.remove()  # limpiar handler default

    level = "DEBUG" if verbose else "INFO"

    # Consola: formato compacto y coloreado
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Archivo: rotación diaria
    log_dir = log_dir or Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "ocr_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    _CONFIGURED = True