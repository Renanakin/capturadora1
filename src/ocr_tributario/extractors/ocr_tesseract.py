"""OCR con Tesseract (Fase 5.3)."""

from __future__ import annotations

from pathlib import Path

import pytesseract
from loguru import logger
from PIL import Image

from ocr_tributario.config.schema import OcrConfig


def configure_tesseract(tesseract_cmd: Path | str, tessdata_prefix: Path | str) -> None:
    """Fija rutas del binario y de los datos de idioma."""
    pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
    # tesseract respeta TESSDATA_PREFIX a nivel de proceso
    import os
    os.environ["TESSDATA_PREFIX"] = str(tessdata_prefix)


def _build_tesseract_config(cfg: OcrConfig, psm: int | None = None) -> str:
    """Construye el config de Tesseract.

    IMPORTANTE: pytesseract en Windows usa shlex.split(posix=False) sobre este
    string. NO usar comillas dentro del whitelist (rompe el parser) ni
    caracteres no-ASCII (e.g. °) - pasan como tokens sucios.
    Por eso la whitelist se omite en esta versión: el OCR general funciona
    mejor sin restricción. Para OCR de dígitos puros, usar llamada dedicada.
    """
    return f"--psm {psm if psm is not None else cfg.psm}"


def ocr_image(
    image_path: Path | str,
    cfg: OcrConfig,
    whitelist: bool = False,  # deprecated: ver docstring de _build_tesseract_config
) -> str:
    """OCR completo sobre una imagen de archivo."""
    img = Image.open(image_path)
    config = _build_tesseract_config(cfg)
    try:
        return pytesseract.image_to_string(img, lang=cfg.lang, config=config)
    except pytesseract.TesseractNotFoundError as exc:
        logger.error(f"Tesseract no encontrado: {exc}")
        raise


def ocr_array(img_array, cfg: OcrConfig, whitelist: bool = False) -> str:
    """OCR sobre un numpy array (BGR o grayscale)."""
    if hasattr(img_array, "shape") and len(img_array.shape) == 3:
        from cv2 import cv2
        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img_array)
    config = _build_tesseract_config(cfg)
    try:
        return pytesseract.image_to_string(img, lang=cfg.lang, config=config)
    except pytesseract.TesseractNotFoundError as exc:
        logger.error(f"Tesseract no encontrado: {exc}")
        raise


def ocr_array_multi_psm(
    img_array, cfg: OcrConfig, psms: tuple[int, ...] = (3, 4, 6, 11)
) -> tuple[str, dict]:
    """Prueba múltiples PSM y devuelve el texto con más campos extraíbles.

    Estrategia de ranking: cuenta matches de RUT/Fecha/Total en cada pasada y
    devuelve la que tenga más matches.
    """
    import re
    from ocr_tributario.validators.regex_patterns import (
        _RUT_INLINE,
        extract_date,
        extract_total,
    )

    candidates: list[tuple[int, str, int]] = []  # (score, text, psm)
    for psm in psms:
        config = _build_tesseract_config(cfg, psm=psm)
        try:
            text = pytesseract.image_to_string(
                img_array, lang=cfg.lang, config=config
            )
        except Exception as exc:
            logger.warning(f"OCR PSM={psm} falló: {exc}")
            continue
        score = 0
        if _RUT_INLINE.search(text):
            score += 5
        if extract_date(text):
            score += 3
        if extract_total(text):
            score += 4
        # bonus por longitud razonable
        if len(text.strip()) > 50:
            score += 1
        candidates.append((score, text, psm))

    if not candidates:
        return "", {"psm_chosen": None, "scores": {}}

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_text, best_psm = candidates[0]
    scores = {psm: score for score, _, psm in candidates}
    logger.debug(f"Multi-PSM elegido: {best_psm} (score={best_score}, scores={scores})")
    return best_text, {"psm_chosen": best_psm, "scores": scores}


def ocr_with_anchors(image_path: Path | str, cfg: OcrConfig) -> dict[str, str]:
    """OCR con image_to_data y extracción por palabras clave ancla.

    Busca 'TOTAL', 'NETO', 'RUT', 'FACTURA' y devuelve el texto a la derecha
    de cada ancla. Útil cuando no hay recuadro rojo.
    """
    img = Image.open(image_path)
    data = pytesseract.image_to_data(
        img, lang=cfg.lang, config=f"--psm {cfg.psm}", output_type=pytesseract.Output.DICT
    )

    anchors = {"TOTAL": None, "NETO": None, "RUT": None, "FACTURA": None}
    for i, word in enumerate(data["text"]):
        word_clean = (word or "").strip().upper()
        if word_clean in anchors and anchors[word_clean] is None:
            # tomar siguiente token no vacío
            for j in range(i + 1, min(i + 6, len(data["text"]))):
                nxt = (data["text"][j] or "").strip()
                if nxt:
                    anchors[word_clean] = nxt
                    break

    return {k: v or "" for k, v in anchors.items()}