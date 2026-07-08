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