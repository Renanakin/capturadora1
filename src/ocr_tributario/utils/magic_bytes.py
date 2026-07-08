"""Detección de tipo de archivo por magic bytes (Fase 2)."""

from __future__ import annotations

from pathlib import Path

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def detect_file_type(path: Path) -> str:
    """Devuelve uno de: 'pdf', 'image', 'unknown'.

    Usa los primeros 16 bytes del archivo. No es exhaustivo,
    solo distingue los formatos que nos interesan.
    """
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError:
        return "unknown"

    if head.startswith(_PDF_MAGIC):
        return "pdf"
    if head.startswith(_JPEG_MAGIC):
        return "image"
    if head.startswith(_PNG_MAGIC):
        return "image"
    return "unknown"


def has_extractable_text(pdf_path: Path, min_chars: int = 50) -> bool:
    """True si el PDF tiene capa de texto nativa extraíble con pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return False

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if len(txt.strip()) >= min_chars:
                    return True
        return False
    except Exception:
        return False