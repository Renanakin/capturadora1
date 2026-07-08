"""Extracción por anclas con coordenadas (image_to_data).

Idea: en vez de depender del orden del texto OCR, buscamos palabras clave
('TOTAL', 'NETO', 'R.U.T', 'FACTURA', 'BOLETA', 'FECHA') y leemos los
tokens a la derecha o abajo según coordenadas. Esto es robusto a:
- texto en múltiples columnas
- palabras con OCR ruidoso en el medio
- líneas que se cortan mal
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pytesseract
from loguru import logger

from ocr_tributario.config.schema import OcrConfig


# Anclas y los campos a los que mapean
ANCHOR_GROUPS: dict[str, list[str]] = {
    "total": ["TOTAL"],
    "neto": ["NETO", "MONTO", "VALOR"],
    "iva": ["IVA"],
    "rut": ["RUT", "R.U.T", "R.U.T."],
    "factura": ["FACTURA"],
    "boleta": ["BOLETA"],
    "fecha": ["FECHA"],
    "emision": ["EMISION", "EMISIÓN"],
    "folio": ["FOLIO", "N°", "Nº", "N*"],
    "proveedor": ["RAZÓN", "RAZON", "EMPRESA", "NOMBRE"],
}

# Stoppers: palabras que indican fin del bloque que queremos leer
TEXT_STOPPERS = {
    "BOLETA", "FACTURA", "GIRO", "DIRECCION", "DIRECCIÓN", "COMUNA",
    "CIUDAD", "S.I.I", "S.I.I.", "FECHA", "TELEFONO", "TELÉFONO", "EMAIL",
    "E-MAIL", "SEÑOR", "SEÑORES", "CONTACTO", "COMPRA", "ARTICULO",
    "ARTÍCULO", "VALOR", "EFECTIVO", "TARJETA", "DEBITO", "DÉBITO",
    "CREDITO", "CRÉDITO", "CAJA", "NETO", "IVA", "TOTAL", "SUBTOTAL",
    "DESCUENTO", "RECARGO", "CANCEL", "ARTURO", "HOSPITAL", "SERVICIO",
    "MONTO", "CANTIDAD", "RUT", "R.U.T", "R.U.T.", "FOLIO",
}


@dataclass
class AnchorHit:
    """Una coincidencia de ancla con los tokens cercanos capturados."""
    anchor: str
    anchor_text: str
    right_token: str | None = None
    below_token: str | None = None
    line_after: list[str] = field(default_factory=list)


@dataclass
class AnchorExtraction:
    hits: dict[str, AnchorHit] = field(default_factory=dict)
    rut: str | None = None
    total: int | None = None
    neto: int | None = None
    iva: int | None = None
    fecha: str | None = None
    folio: int | None = None
    proveedor: str | None = None

    def as_dict(self) -> dict:
        return {
            "rut": self.rut,
            "total": self.total,
            "neto": self.neto,
            "iva": self.iva,
            "fecha": self.fecha,
            "folio": self.folio,
            "proveedor": self.proveedor,
        }


def _normalize_word(w: str) -> str:
    return (w or "").strip().upper().rstrip(".,:;")


def _y_tolerance(height: int) -> int:
    """Tolerancia vertical según la altura típica de las palabras."""
    return max(8, height // 2)


def _x_distance_ok(x1: int, x2: int, max_gap: int = 250) -> bool:
    return 0 <= (x2 - x1) <= max_gap


def _find_anchor_words(data: dict) -> list[tuple[int, str, int, int, int, int]]:
    """Devuelve (idx, word_upper, x, y, w_px, h_px) de palabras que matchean alguna ancla."""
    out = []
    for i, (txt, x, y, w, h) in enumerate(
        zip(data["text"], data["left"], data["top"], data["width"], data["height"])
    ):
        norm = _normalize_word(txt)
        if not norm:
            continue
        for anchor_name, keywords in ANCHOR_GROUPS.items():
            for kw in keywords:
                if norm == kw.upper() or norm == kw.upper().rstrip("."):
                    out.append((i, norm, x, y, w, h, anchor_name))
                    break
                # Match parcial: "R.U.T" o "R.U.T." o "R.U.T:" con puntuación
                if norm.rstrip(".:") == kw.upper().rstrip("."):
                    out.append((i, norm, x, y, w, h, anchor_name))
                    break
    return out


def _next_right(
    data: dict,
    anchor_idx: int,
    anchor_x: int,
    anchor_y: int,
    anchor_h: int,
    same_line: bool = True,
) -> str | None:
    """Primer token no vacío a la derecha del ancla, misma línea (tolerancia Y)."""
    tol = _y_tolerance(anchor_h)
    best: tuple[int, str] | None = None
    for i in range(anchor_idx + 1, len(data["text"])):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        x = data["left"][i]
        y = data["top"][i]
        h = data["height"][i] or anchor_h
        if same_line and abs(y - anchor_y) > tol:
            break  # ya pasamos a otra línea
        if not _x_distance_ok(anchor_x, x):
            continue
        if _normalize_word(txt) in TEXT_STOPPERS:
            break
        # limpiar prefijos típicos ($ : N°)
        cleaned = re.sub(r"^[\$:N°ºo\*\.]+\s*", "", txt)
        if best is None or x < best[0]:
            best = (x, cleaned)
            break
    return best[1] if best else None


def _line_after(
    data: dict,
    anchor_idx: int,
    anchor_y: int,
    anchor_h: int,
    max_lines: int = 1,
) -> list[str]:
    """Tokens de las siguientes max_lines líneas."""
    out: list[str] = []
    tol = _y_tolerance(anchor_h)
    target_lines = max_lines
    next_line_y = None

    for i in range(anchor_idx + 1, len(data["text"])):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        y = data["top"][i]
        h = data["height"][i] or anchor_h
        if next_line_y is None:
            if y > anchor_y + tol:
                next_line_y = y
            else:
                continue
        else:
            if abs(y - next_line_y) <= tol:
                pass  # misma línea
            elif y > next_line_y + tol:
                # nueva línea
                if target_lines <= 0:
                    break
                target_lines -= 1
                next_line_y = y
            else:
                continue
        out.append(txt)

    return out


def _first_right_of_anchor(
    data: dict,
    anchor_idx: int,
    anchor_name: str,
) -> AnchorHit | None:
    """Lee el token a la derecha del ancla en la misma línea."""
    txt = (data["text"][anchor_idx] or "").strip()
    norm = _normalize_word(txt)
    x = data["left"][anchor_idx]
    y = data["top"][anchor_idx]
    h = data["height"][anchor_idx] or 20

    right = _next_right(data, anchor_idx, x, y, h, same_line=True)

    return AnchorHit(
        anchor=anchor_name,
        anchor_text=norm,
        right_token=right,
    )


def _read_after_anchor_lines(
    data: dict,
    anchor_idx: int,
    anchor_name: str,
    max_lines: int = 2,
) -> AnchorHit | None:
    """Lee las líneas siguientes al ancla (útil para 'R.U.T:' -> RUT del emisor en línea siguiente, etc.)"""
    txt = (data["text"][anchor_idx] or "").strip()
    norm = _normalize_word(txt)
    x = data["left"][anchor_idx]
    y = data["top"][anchor_idx]
    h = data["height"][anchor_idx] or 20

    right = _next_right(data, anchor_idx, x, y, h, same_line=True)
    after = _line_after(data, anchor_idx, y, h, max_lines=max_lines)

    return AnchorHit(
        anchor=anchor_name,
        anchor_text=norm,
        right_token=right,
        line_after=after,
    )


def extract_by_anchors(img_array, cfg: OcrConfig, lang: str | None = None) -> AnchorExtraction:
    """Hace OCR con coordenadas y extrae campos por palabras clave ancla."""
    lang = lang or cfg.lang
    config = f"--psm {cfg.psm}"
    try:
        data = pytesseract.image_to_data(
            img_array,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.error(f"image_to_data falló: {exc}")
        return AnchorExtraction()

    anchor_words = _find_anchor_words(data)
    if not anchor_words:
        return AnchorExtraction()

    extraction = AnchorExtraction()

    for (idx, norm, x, y, w_px, h_px, anchor_name) in anchor_words:
        if anchor_name in {"rut", "fecha", "emision", "folio"}:
            hit = _read_after_anchor_lines(data, idx, anchor_name, max_lines=1)
        else:
            hit = _first_right_of_anchor(data, idx, anchor_name)

        if hit is None:
            continue
        extraction.hits[anchor_name] = hit

    # Resolver campos finales desde los hits
    _resolve_rut(extraction)
    _resolve_total(extraction)
    _resolve_neto_iva(extraction)
    _resolve_fecha(extraction)
    _resolve_folio(extraction)
    _resolve_proveedor(extraction)

    return extraction


# --- Resolución de campos finales ---

_RUT_TOKEN = re.compile(r"\d{1,2}\.?\d{3}\.?\d{3}-[0-9Kk]")


def _resolve_rut(ext: AnchorExtraction) -> None:
    hit = ext.hits.get("rut")
    if not hit:
        return
    candidates: list[str] = []
    if hit.right_token:
        candidates.append(hit.right_token)
    candidates.extend(hit.line_after or [])
    for c in candidates:
        m = _RUT_TOKEN.search(c.replace(" ", ""))
        if m:
            ext.rut = m.group(0)
            return


_MONEY_TOKEN = re.compile(r"[\$]?\s*([\d\.\,]+)")


def _parse_money(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(".", "")
    try:
        return int(float(raw))
    except ValueError:
        return None


def _resolve_total(ext: AnchorExtraction) -> None:
    hit = ext.hits.get("total")
    if not hit:
        return
    raw = hit.right_token or ""
    ext.total = _parse_money(raw)


def _resolve_neto_iva(ext: AnchorExtraction) -> None:
    neto_hit = ext.hits.get("neto")
    if neto_hit and neto_hit.right_token:
        ext.neto = _parse_money(neto_hit.right_token)
    iva_hit = ext.hits.get("iva")
    if iva_hit and iva_hit.right_token:
        ext.iva = _parse_money(iva_hit.right_token)


def _resolve_fecha(ext: AnchorExtraction) -> None:
    from ocr_tributario.validators.regex_patterns import extract_date
    pieces: list[str] = []
    for k in ("fecha", "emision"):
        hit = ext.hits.get(k)
        if not hit:
            continue
        if hit.right_token:
            pieces.append(hit.right_token)
        pieces.extend(hit.line_after or [])
    text = " ".join(pieces)
    if not text:
        return
    ext.fecha = extract_date(text)


def _resolve_folio(ext: AnchorExtraction) -> None:
    hit = ext.hits.get("folio")
    if not hit:
        return
    candidates: list[str] = []
    if hit.right_token:
        candidates.append(hit.right_token)
    candidates.extend(hit.line_after or [])
    for c in candidates:
        m = re.search(r"\d{3,12}", c.replace(".", "").replace(",", ""))
        if m:
            try:
                ext.folio = int(m.group(0))
                return
            except ValueError:
                continue


_BAD_PROVIDER_KW = (
    "VERIFIQUE", "DOCUMENTO", "WWW", "SII", "RES.", "RESOL",
    "TIMBRE", "CONTRIBUYENTE", "DECRETO", "TRANSACCION", "TRANSACCIÓN",
    "PAGUESE", "PÁGUESE", "EFECTIVO", "DEBITO", "DÉBITO", "CREDITO", "CRÉDITO",
    "VALOR", "FECHA", "TOTAL", "IVA", "BOLETA", "FACTURA", "ELECTRONICA",
    "ELECTRÓNICA", "TRAD", "S.I.I", "CURICO", "CURICÓ",
)


def _resolve_proveedor(ext: AnchorExtraction) -> None:
    """El proveedor está típicamente:
    a) en la línea siguiente al RUT del emisor, o
    b) como la primera palabra cerca del RUT (a la derecha o debajo).
    """
    # Estrategia: usar los hits para construir candidatos
    candidates: list[str] = []

    rut_hit = ext.hits.get("rut")
    if rut_hit:
        candidates.extend(rut_hit.line_after or [])

    proveedor_hit = ext.hits.get("proveedor")
    if proveedor_hit:
        if proveedor_hit.right_token:
            candidates.insert(0, proveedor_hit.right_token)
        candidates.extend(proveedor_hit.line_after or [])

    for cand in candidates:
        cand_clean = cand.strip()
        if not cand_clean:
            continue
        upper = cand_clean.upper()
        if any(k in upper for k in _BAD_PROVIDER_KW):
            continue
        if len(cand_clean) < 4 or len(cand_clean) > 60:
            continue
        if re.search(r"\d{4,}", cand_clean):
            continue
        ext.proveedor = cand_clean
        return