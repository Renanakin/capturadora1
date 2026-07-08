"""Clasificador de tipo de documento tributario chileno.

Heurísticas basadas en keywords + estructura. Decide qué parser aplicar.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

from loguru import logger

from ocr_tributario.services.ocr_easy import OCRResult


class DocumentType(str, Enum):
    FACTURA_ELECTRONICA = "factura_electronica"
    BOLETA_ELECTRONICA = "boleta_electronica"
    NOTA_CREDITO = "nota_credito"
    GUIA_DESPACHO = "guia_despacho"
    DTE_GENERICO = "dte_generico"
    DESCONOCIDO = "desconocido"


# Keywords con peso (mayor = más confianza)
_KEYWORDS: dict[DocumentType, dict[str, int]] = {
    DocumentType.FACTURA_ELECTRONICA: {
        "FACTURA ELECTRONICA": 10,
        "FACTURA ELECTRÓNICA": 10,
        "FACTURA DE COMPRA": 5,
        "FACTURA DE VENTA": 5,
        "FACTURA EXENTA": 8,
    },
    DocumentType.BOLETA_ELECTRONICA: {
        "BOLETA ELECTRONICA": 10,
        "BOLETA ELECTRÓNICA": 10,
        "BOLETA DE VENTA": 5,
        "BOLETA EXENTA": 6,
        "BOLETA HONORARIOS": 4,
    },
    DocumentType.NOTA_CREDITO: {
        "NOTA DE CREDITO": 10,
        "NOTA DE CRÉDITO": 10,
        "NOTA CREDITO": 8,
        "NOTA CRÉDITO": 8,
    },
    DocumentType.GUIA_DESPACHO: {
        "GUIA DE DESPACHO": 10,
        "GUÍA DE DESPACHO": 10,
    },
}

# Marcadores genéricos DTE (cuando no se puede distinguir subtipo)
_DTE_GENERIC_MARKERS = ("RUT", "FOLIO", "S.I.I", "SII")


def _score_type(text_upper: str, keywords: dict[str, int]) -> int:
    s = 0
    for kw, weight in keywords.items():
        if kw in text_upper:
            s += weight
    return s


def _has_dte_markers(text_upper: str) -> bool:
    """¿Tiene al menos 2 marcadores DTE típicos?"""
    found = sum(1 for m in _DTE_GENERIC_MARKERS if m in text_upper)
    return found >= 2


def classify_document(ocr_result: OCRResult | str) -> DocumentType:
    """Clasifica el documento a partir del texto OCR.

    Acepta un OCRResult (usa full_text) o un string directo.
    """
    if isinstance(ocr_result, OCRResult):
        text = ocr_result.full_text
    else:
        text = ocr_result

    text_upper = text.upper()

    scores: dict[DocumentType, int] = {}
    for doc_type, keywords in _KEYWORDS.items():
        scores[doc_type] = _score_type(text_upper, keywords)

    # Encontrar el tipo con mayor score
    best_type = max(scores, key=scores.get)  # type: ignore
    best_score = scores[best_type]

    if best_score >= 8:
        logger.debug(f"Clasificado como {best_type.value} (score={best_score})")
        return best_type

    # Si no hay match fuerte pero hay marcadores DTE, clasificar como genérico
    if _has_dte_markers(text_upper):
        logger.debug(f"Clasificado como dte_generico (sin keywords fuertes)")
        return DocumentType.DTE_GENERICO

    logger.debug(f"Documento desconocido (scores={scores})")
    return DocumentType.DESCONOCIDO


def is_dte(doc_type: DocumentType) -> bool:
    """True si es un DTE (factura, boleta, NC, guía, genérico)."""
    return doc_type in {
        DocumentType.FACTURA_ELECTRONICA,
        DocumentType.BOLETA_ELECTRONICA,
        DocumentType.NOTA_CREDITO,
        DocumentType.GUIA_DESPACHO,
        DocumentType.DTE_GENERICO,
    }