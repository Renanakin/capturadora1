"""Escaneo de directorios (Fase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from loguru import logger

from ocr_tributario.utils.magic_bytes import detect_file_type


@dataclass(frozen=True)
class DocumentInput:
    path: Path
    file_type: str  # 'pdf' | 'image' | 'unknown'

    @property
    def name(self) -> str:
        return self.path.name


_SUPPORTED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def iter_supported_files(input_dir: Path) -> Iterator[Path]:
    """Itera recursivamente sobre archivos con extensiones soportadas."""
    if not input_dir.exists():
        logger.warning(f"Carpeta de entrada no existe: {input_dir}")
        return
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in _SUPPORTED_EXT:
            yield path


def scan_directory(input_dir: Path) -> list[DocumentInput]:
    """Devuelve todos los documentos detectables en input_dir."""
    docs: list[DocumentInput] = []
    for path in iter_supported_files(input_dir):
        ftype = detect_file_type(path)
        if ftype == "unknown":
            logger.warning(f"Tipo de archivo no reconocido, se omite: {path}")
            continue
        docs.append(DocumentInput(path=path, file_type=ftype))
    logger.info(f"Encontrados {len(docs)} documentos en {input_dir}")
    return docs