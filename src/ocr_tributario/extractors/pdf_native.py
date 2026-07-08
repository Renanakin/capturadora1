"""Extractor para PDFs nativos (Fase 5.1)."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
from loguru import logger


_NRO_FACTURA_PATTERNS = [
    re.compile(r"(?:factura|boleta|doc(?:umento)?\.?)\s*n[°ºo\.]?\s*(\d[\d\.\-]*)", re.IGNORECASE),
    re.compile(r"\bN[°ºo\.]?\s*(\d[\d\.\-]{2,})\b", re.IGNORECASE),
]

_FECHA_PATTERNS = [
    re.compile(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b"),
]

_TOTAL_PATTERNS = [
    re.compile(r"total\s*[:\$]?\s*\$?\s*([\d\.\,]+)", re.IGNORECASE),
    re.compile(r"\bTOTAL\s+([\d\.\,]+)\b"),
]


def _first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return None


def extract_native_pdf_data(path: Path) -> dict[str, str | None]:
    """Lee texto de un PDF nativo. Devuelve claves crudas para que el parser las trabaje."""
    try:
        with pdfplumber.open(path) as pdf:
            texts: list[str] = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t:
                    texts.append(t)
        full_text = "\n".join(texts)
    except Exception as exc:
        logger.error(f"pdfplumber falló leyendo {path.name}: {exc}")
        return {"raw_text": "", "provider_raw": None, "sii_raw": None, "totals_raw": None, "fecha_raw": None, "nro_raw": None}

    return {
        "raw_text": full_text,
        "provider_raw": None,  # pdfplumber no entrega bounding boxes gratis; usamos heurística sobre el texto
        "sii_raw": _first_match([re.compile(r"RUT[:\s]*([\d\.\-]+K?)", re.IGNORECASE)], full_text),
        "totals_raw": _first_match(_TOTAL_PATTERNS, full_text),
        "fecha_raw": _first_match(_FECHA_PATTERNS, full_text),
        "nro_raw": _first_match(_NRO_FACTURA_PATTERNS, full_text),
    }