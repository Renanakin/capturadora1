"""Parsers deterministas: fecha, monto, folio, RUT desde texto crudo (Fase 6)."""

from __future__ import annotations

import re
from datetime import date, datetime

from ocr_tributario.validators.rut import validate_rut

_DATE_PATTERNS = [
    # dd/mm/yyyy o dd-mm-yyyy o dd.mm.yyyy (con lookahead de no-dígito
    # para tolerar concatenación con letras, ej. "25/04/2022AID:...").
    re.compile(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})(?=[^\d]|$)"),
    # dd/mm/yyyy + hora concatenada "25/04/202209:29:50" (Transbank)
    re.compile(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\d{2}:\d{2}:\d{2}"),
]

_MONTHS_ES = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "set": 9, "sept": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
    "jan": 1, "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_MONTHS_ORDERED = sorted(_MONTHS_ES.keys(), key=len, reverse=True)
_MONTH_TEXT = re.compile(
    r"\b(\d{1,2})\s*(?:de\s+)?("
    + "|".join(re.escape(k) for k in _MONTHS_ORDERED)
    + r")\b(?:\s*(?:de\s+)?(?:del?\s+)?(\d{2,4}))?",
    re.IGNORECASE,
)

# dd-mmm-yyyy / dd-mmm-yy con guión como separador (facturas chilenas:
# "Fecha de Emisión : 01-dic-2025"). El guión no se interpreta como signo.
_DATE_TEXT_GUION = re.compile(
    r"\b(\d{1,2})[\-\u2013\u2014]("
    + "|".join(re.escape(k) for k in _MONTHS_ORDERED)
    + r")[\-\u2013\u2014](\d{2,4})\b",
    re.IGNORECASE,
)

_MONTH_TEXT_EN = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in _MONTHS_ORDERED)
    + r")\b\s+(\d{1,2})(?:st|nd|rd|th)?[\,\s]+(\d{2,4})",
    re.IGNORECASE,
)


def extract_date(text: str | None) -> date | None:
    """Devuelve la primera fecha válida en formato YYYY-MM-DD.

    Acepta dd/mm/yyyy, '15 de marzo de 2024' y '01-dic-2025' (con guión).
    """
    if not text:
        return None

    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            d_str, mo_str, y_str = m.groups()
            try:
                d, mo = int(d_str), int(mo_str)
                y = int(y_str)
                if y < 100:
                    y += 2000 if y < 70 else 1900
                if not (1 <= mo <= 12 and 1 <= d <= 31):
                    continue
                return date(y, mo, d)
            except ValueError:
                continue

    # Formato dd-mmm-yyyy con guión (factura Movistar, etc.)
    m = _DATE_TEXT_GUION.search(text)
    if m:
        d_str, mo_name, y_str = m.groups()
        mo = _MONTHS_ES.get(mo_name.lower())
        if mo and (1 <= int(d_str) <= 31):
            y = int(y_str)
            if y < 100:
                y += 2000 if y < 70 else 1900
            try:
                return date(y, mo, int(d_str))
            except ValueError:
                pass

    m = _MONTH_TEXT.search(text)
    if m:
        d_str, mo_name, y_str = m.groups()
        mo = _MONTHS_ES.get(mo_name.lower())
        if mo and (1 <= int(d_str) <= 31):
            y = int(y_str) if y_str else datetime.now().year
            if y < 100:
                y += 2000 if y < 70 else 1900
            try:
                return date(y, mo, int(d_str))
            except ValueError:
                pass

    m_en = _MONTH_TEXT_EN.search(text)
    if m_en:
        mo_name, d_str, y_str = m_en.groups()
        mo = _MONTHS_ES.get(mo_name.lower())
        if mo and (1 <= int(d_str) <= 31):
            y = int(y_str)
            if y < 100:
                y += 2000 if y < 70 else 1900
            try:
                return date(y, mo, int(d_str))
            except ValueError:
                pass

    return None


_TOTAL_PATTERNS = [
    # "Total: $1.234" / "Total $1.234" / "Total\n$1.234" / "Total $ :\n1.200"
    # Tolera OCR confundiendo $ con S, dos puntos, saltos de línea y hasta
    # 15 caracteres entre "total" y el número.
    re.compile(r"total\b[^\d]{0,15}?([\d\.\,]{3,})", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bTOTAL\s+([\d\.\,]+)"),
    re.compile(r"(?:monto|total)\s+a\s+pagar\b[^\d]{0,15}?([\d\.\,]{3,})", re.IGNORECASE | re.DOTALL),
    re.compile(r"(?<![A-Za-z0-9])\$\s*([\d\.\,]{3,})", re.IGNORECASE),
]


def extract_total(text: str | None) -> int | None:
    """Lee el total de la factura (entero en CLP). Tolera separadores de miles."""
    if not text:
        return None
    for pat in _TOTAL_PATTERNS:
        m = pat.search(text)
        if m:
            return _parse_money(m.group(1))
    return None


def _parse_money(raw: str) -> int | None:
    raw = raw.strip().replace(" ", "")
    if not raw:
        return None
        
    import re
    # Si termina con .XX o ,XX (exactamente 2 dígitos), quitamos los centavos.
    if re.search(r'[\.\,]\d{2}$', raw):
        raw = raw[:-3]
    # O si termina con .X o ,X (1 dígito)
    elif re.search(r'[\.\,]\d{1}$', raw):
        raw = raw[:-2]
        
    raw = raw.replace(".", "").replace(",", "")
    
    try:
        return int(raw)
    except ValueError:
        return None


_FOLIO_PATTERNS = [
    # "N° 001111111" / "N* 35665" / "Nº 12345"
    re.compile(r"\bN[°ºo\*\.]?\s*(\d{3,12})\b"),
    # "FACTURA N° 12345"
    re.compile(r"(?:factura|boleta)\s*n[°ºo\*\.]?\s*(\d{3,12})", re.IGNORECASE),
    # "BOLETA ELECTRÓNICA N° 001111111" - acepta espacios
    re.compile(r"(?:factura|boleta)\s+(?:electr[oó]nica\s+)?n[°ºo\*\.]?\s*(\d{3,12})", re.IGNORECASE),
    re.compile(r"\bfolio\s*n[°ºo\*\.]?\s*(\d{1,10})", re.IGNORECASE),
    # Folio suelto precedido por "boleta" o "factura" sin "N°"
    re.compile(r"(?:factura|boleta)\s+(\d{4,10})\b", re.IGNORECASE),
    # "NRO 1234" / "Nro: 1234" - boletas chilenas
    re.compile(r"\bNRO\.?\s*[:N°ºo\.]*\s*(\d{2,12})\b", re.IGNORECASE),
]


def extract_folio(text: str | None) -> int | None:
    if not text:
        return None
    for pat in _FOLIO_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1).replace(".", "").replace("-", ""))
            except ValueError:
                continue
    return None


_RUT_INLINE = re.compile(
    r"R\.?U\.?T\.?\s*[:N°ºo\.]*\s*"
    r"(\d{1,2}\.?\d{3}\.?\d{3}[\-\u2013\u2014][0-9Kk])",
    re.IGNORECASE,
)

# RUT fallback: cualquier patrón de RUT sin necesidad de etiqueta explícita
_RUT_FALLBACK = re.compile(
    r"\b(\d{1,2}\.?\d{3}\.?\d{3}[\-\u2013\u2014][0-9Kk])\b",
    re.IGNORECASE,
)

# RUT sin DV (caso "RUT: 76.000.000" en boleta Banchile y similares)
# Solo se aplica cuando hay keyword "RUT" explícita para evitar falsos positivos
# con cualquier número con formato XX.XXX.XXX.
_RUT_NO_DV = re.compile(
    r"R\.?U\.?T\.?\s*[:N°ºo\.]*\s*"
    r"(\d{1,2}(?:\.\d{3}){1,2})(?![-\dKk])",
    re.IGNORECASE,
)


def extract_rut(text: str | None) -> str | None:
    """Encuentra y valida el primer RUT en el texto.

    Primero busca con marca explícita 'RUT'/'R.U.T' previa (reduce falsos
    positivos). Si no encuentra, hace fallback a cualquier patrón con
    formato RUT que apruebe la validación matemática módulo 11. Como
    último recurso acepta un RUT sin DV (e.g. "RUT: 76.000.000" en
    boletas chilenas) marcado con score bajo por el parser.
    """
    if not text:
        return None

    # 1. Búsqueda explícita (más segura)
    for m in _RUT_INLINE.finditer(text):
        candidate = m.group(1)
        canonico = validate_rut(candidate)
        if canonico:
            return canonico

    # 2. Fallback: buscar cualquier patrón de RUT válido
    for m in _RUT_FALLBACK.finditer(text):
        candidate = m.group(1)
        canonico = validate_rut(candidate)
        if canonico:
            return canonico

    # 3. Último recurso: RUT explícito sin DV ("RUT: 76.000.000")
    m = _RUT_NO_DV.search(text)
    if m:
        return m.group(1)

    return None