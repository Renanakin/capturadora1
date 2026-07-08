"""Normalizadores de texto (Fase 6)."""

from __future__ import annotations

import re
import unicodedata


def normalize_provider_name(raw: str | None) -> str | None:
    """Trim, colapsa espacios, mayúsculas selectivas (primera letra de cada palabra)."""
    if not raw:
        return None
    s = unicodedata.normalize("NFKC", str(raw))
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    # Title case respetando palabras cortas usuales
    small = {"de", "del", "la", "las", "los", "y", "e", "s.a.", "s.a", "spa", "ltda", "cia"}
    parts = []
    for token in s.split(" "):
        low = token.lower()
        if low in small:
            parts.append(low)
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def normalize_mes(fecha_iso: str | None) -> str | None:
    """YYYY-MM-DD -> 'YYYY-MM' para agrupar en planilla."""
    if not fecha_iso or len(fecha_iso) < 7:
        return None
    return fecha_iso[:7]


def extract_provider(text: str | None, rut_canonico: str | None = None) -> str | None:
    """Heurística simple para extraer el nombre del proveedor.

    Estrategia:
      1) Bloque de texto inmediatamente después del RUT del emisor.
      2) Primera línea en MAYÚSCULAS sin dígitos (>= 70% mayúsculas).
      3) (desactivado por ruido) Primera línea razonable.
    """
    if not text:
        return None

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None

    stoppers = re.compile(
        r"^(BOLETA|FACTURA|GIRO|DIRECCI[ÓO]N|COMUNA|CIUDAD|S\.?I\.?I\.?|"
        r"FECHA|R\.?U\.?T\.?|TEL[EÉ]FONO|E-?MAIL|SEÑOR|SE[ÑN]OR\(?ES\)?|"
        r"CONTACTO|COMPRA|ART[IÍ]CULO|VALOR|EFECTIVO|TARJETA|D[EÉ]BITO|C[RÉ]EDITO|"
        r"CAJA|NETO|IVA|TOTAL|SUBTOTAL|DESCUENTO|RECARGO|CANCEL|"
        r"ARTURO|HOSPITAL|SERVICIO|M[OÓ]NTO|CANTIDAD|N[°ºo\*\.]?)",
        re.IGNORECASE,
    )

    # Heurística 1: bloque después del RUT
    if rut_canonico:
        bare = rut_canonico.replace(".", "").replace("-", "")
        for i, line in enumerate(lines):
            if re.search(r"R\.?U\.?T\.?\s*[:N°ºo\.]*\s*" + re.escape(bare[:8]), line, re.IGNORECASE):
                for j in range(i + 1, min(i + 5, len(lines))):
                    cand = lines[j]
                    if stoppers.match(cand):
                        continue
                    if re.search(r"R\.?U\.?T\.?", cand, re.IGNORECASE):
                        continue
                    if re.search(r"\d{4,}", cand):
                        continue
                    # Solo aceptar si parece un nombre (>= 70% mayúsculas o title case)
                    if _looks_like_provider(cand):
                        return normalize_provider_name(cand)
                break

    # Heurística 2: primera línea con mayoría de MAYÚSCULAS y sin dígitos
    for line in lines:
        if stoppers.match(line):
            continue
        if re.search(r"\d", line):
            continue
        if _looks_like_provider(line):
            return normalize_provider_name(line)

    return None


def _looks_like_provider(line: str) -> bool:
    """Filtro: parece nombre de empresa? (sin palabras comunes del SII)."""
    if len(line) < 4 or len(line) > 80:
        return False
    bad_keywords = (
        "VERIFIQUE", "DOCUMENTO", "WWW", "SII", "RES.", "RESOL",
        "TIMBRE", "CONTRIBUYENTE", "DECRETO", "TRANSACCION", "TRANSACCIÓN",
        "PAGUESE", "PÁGUESE", "EFECTIVO", "DEBITO", "DÉBITO", "CREDITO", "CRÉDITO",
        "VALOR", "FECHA", "TOTAL", "IVA",
    )
    upper = line.upper()
    if any(k in upper for k in bad_keywords):
        return False
    letters = [c for c in line if c.isalpha()]
    if not letters or len(letters) < 3:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio >= 0.7