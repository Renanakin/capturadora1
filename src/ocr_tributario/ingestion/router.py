"""Enrutador: decide ruta de procesamiento (Fase 2)."""

from __future__ import annotations

from typing import Literal

from loguru import logger

from ocr_tributario.ingestion.scanner import DocumentInput
from ocr_tributario.utils.magic_bytes import detect_file_type, has_extractable_text

Route = Literal["pdf_native", "pdf_image", "image", "unknown"]


def route(doc: DocumentInput) -> Route:
    """Decide por dónde procesar el documento.

    - PDF con texto extraíble -> pdf_native (pdfplumber, sin OCR)
    - PDF sin texto           -> pdf_image (render + OCR)
    - Imagen                  -> image (OCR)
    """
    ftype = doc.file_type or detect_file_type(doc.path)

    if ftype == "pdf":
        if has_extractable_text(doc.path):
            logger.debug(f"→ pdf_native: {doc.name}")
            return "pdf_native"
        logger.debug(f"→ pdf_image: {doc.name}")
        return "pdf_image"

    if ftype == "image":
        logger.debug(f"→ image: {doc.name}")
        return "image"

    logger.warning(f"Ruta desconocida para {doc.name}")
    return "unknown"