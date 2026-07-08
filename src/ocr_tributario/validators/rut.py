"""Validador y normalizador de RUT chileno (Módulo 11) - Fase 6."""

from __future__ import annotations

import re

# Acepta: 12345678-5, 12.345.678-5, 12345678K, 12345678k
_RUT_CLEAN = re.compile(r"[^0-9kK]")


def clean_rut(raw: str | None) -> str | None:
    """Quita todo lo que no sea dígito o K, devuelve 'NNNNNNNNDV' o None."""
    if not raw:
        return None
    cleaned = _RUT_CLEAN.sub("", str(raw)).upper()
    if len(cleaned) < 2:
        return None
    body, dv = cleaned[:-1], cleaned[-1]
    if not body.isdigit():
        return None
    return f"{body}{dv}"


def _modulo11_dv(body: str) -> str:
    """Calcula dígito verificador para el cuerpo del RUT (sin DV)."""
    s, mul = 0, 2
    for d in reversed(body):
        s += int(d) * mul
        mul = mul + 1 if mul < 7 else 2
    resto = s % 11
    dv = 11 - resto
    if dv == 11:
        return "0"
    if dv == 10:
        return "K"
    return str(dv)


def validate_rut(raw: str | None) -> str | None:
    """Limpia y verifica DV contra Módulo 11. Devuelve RUT canónico o None."""
    cleaned = clean_rut(raw)
    if cleaned is None:
        return None
    body, dv = cleaned[:-1], cleaned[-1]
    expected = _modulo11_dv(body)
    if dv != expected:
        return None
    # Formato canónico: 12.345.678-5
    rev = body[::-1]
    groups = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    formatted = ".".join(g[::-1] for g in reversed(groups)) + f"-{dv}"
    return formatted


def format_rut(rut_canonico: str) -> str:
    """Aplica el formato con puntos y guión. Ya validado se asume."""
    body, dv = rut_canonico[:-1], rut_canonico[-1]
    rev = body[::-1]
    groups = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    return ".".join(g[::-1] for g in reversed(groups)) + f"-{dv}"