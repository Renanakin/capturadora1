"""Clasificador de tipo de documento tributario chileno.

Heurísticas basadas en keywords + estructura. Decide qué parser aplicar.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

from loguru import logger

from ocr_tributario.services.ocr_paddle import OCRResult


class DocumentType(str, Enum):
    FACTURA_ELECTRONICA = "factura_electronica"
    BOLETA_ELECTRONICA = "boleta_electronica"
    NOTA_CREDITO = "nota_credito"
    GUIA_DESPACHO = "guia_despacho"
    DTE_GENERICO = "dte_generico"
    CEDULA = "cedula"
    INVOICE_EXTRANJERA = "invoice_extranjera"
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
    DocumentType.CEDULA: {
        "CEDULA DE IDENTIDAD": 10,
        "CÉDULA DE IDENTIDAD": 10,
        "REPUBLICA DE CHILE": 5,
        "REPÚBLICA DE CHILE": 5,
        "SERVICIO DE REGISTRO CIVIL": 8,
    },
    DocumentType.INVOICE_EXTRANJERA: {
        "INVOICE": 10,
        "RECEIPT": 10,
        "GOOGLE PLAY": 10,
    },
}

# Marcadores genéricos DTE (cuando no se puede distinguir subtipo)
_DTE_GENERIC_MARKERS = ("RUT", "FOLIO", "S.I.I", "SII")

# Sustituciones de errores típicos de OCR sobre keywords tributarios.
# Aplicadas ANTES del matching para tolerar typos como "ELECTRONCA",
# "TUCTRONCA", "BOLETA LLÉCTRONICA", etc.
_OCR_TYPO_MAP: list[tuple[re.Pattern[str], str]] = [
    # ELECTRONCA / TUCTRONCA / LLECTRONICA / etc. → ELECTRONICA
    (re.compile(r"[ELT][Ll]?[EÉ]?[Cc]?[TC]?[TC]?[R]?[OÓ]?[N]?[C][AÁ]", re.IGNORECASE), "ELECTRONICA"),
    # Normalizar vocales repetidas / acentos
    (re.compile(r"\bFACTUR[ÁA]\b", re.IGNORECASE), "FACTURA"),
    (re.compile(r"\bBOLET[ÁA]\b", re.IGNORECASE), "BOLETA"),
    (re.compile(r"\bCR[EÉ]DIT[OÓ]\b", re.IGNORECASE), "CREDITO"),
    # Variantes OCR de BOLETA (BOLETA / BOLCTA / BOLTTA)
    (re.compile(r"\bBO[Ll][CE]?[TC]?[TC]?[AÁ]\b", re.IGNORECASE), "BOLETA"),
    # Variantes OCR de FACTURA (FASTUNA / FACTURA)
    (re.compile(r"\bF[AE]S?T?U[RN][AÁ]\b", re.IGNORECASE), "FACTURA"),
    # Quitar espacios entre palabras clave (FASTUNA TUCTRONCA → FACTURA ELECTRONICA)
    (re.compile(r"\s+", re.IGNORECASE), " "),
]


def _normalize_ocr_text(text: str) -> str:
    """Normaliza typos típicos de OCR para mejorar clasificación.

    No modifica el texto original, solo devuelve una versión "limpia"
    que se usa para el matching de keywords. El original se conserva
    en DTEFields.raw_text.
    """
    out = text
    for pattern, repl in _OCR_TYPO_MAP[:-1]:  # último es colapso de espacios
        out = pattern.sub(repl, out)
    out = _OCR_TYPO_MAP[-1][0].sub(_OCR_TYPO_MAP[-1][1], out)  # collapse spaces
    return out


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
    # Aplicar normalización tolerante a OCR (no destructiva sobre original)
    text_normalized = _normalize_ocr_text(text_upper)

    scores: dict[DocumentType, int] = {}
    # Matchear contra AMBAS versiones: original (keywords exactos)
    # y normalizada (tolerante a typos OCR).
    for doc_type, keywords in _KEYWORDS.items():
        score_raw = _score_type(text_upper, keywords)
        score_norm = _score_type(text_normalized, keywords)
        scores[doc_type] = max(score_raw, score_norm)

    # Encontrar el tipo con mayor score
    best_type = max(scores, key=scores.get)  # type: ignore
    best_score = scores[best_type]

    if best_score >= 8:
        logger.debug(f"Clasificado como {best_type.value} (score={best_score})")
        return best_type

    # Si no hay match fuerte pero hay marcadores DTE, clasificar como genérico
    if _has_dte_markers(text_upper) or _has_dte_markers(text_normalized):
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
        DocumentType.INVOICE_EXTRANJERA,
    }