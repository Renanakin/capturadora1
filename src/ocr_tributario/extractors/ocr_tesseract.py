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


def ocr_image(
    image_path: Path | str,
    cfg: OcrConfig,
    whitelist: bool = True,
) -> str:
    """OCR completo sobre una imagen de archivo."""
    img = Image.open(image_path)
    config = f"--psm {cfg.psm}"
    if whitelist:
        config += f' -c tessedit_char_whitelist="{cfg.whitelist}"'
    try:
        return pytesseract.image_to_string(img, lang=cfg.lang, config=config)
    except pytesseract.TesseractNotFoundError as exc:
        logger.error(f"Tesseract no encontrado: {exc}")
        raise


def ocr_array(img_array, cfg: OcrConfig, whitelist: bool = True) -> str:
    """OCR sobre un numpy array (BGR o grayscale)."""
    if hasattr(img_array, "shape") and len(img_array.shape) == 3:
        from cv2 import cv2
        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img_array)
    config = f"--psm {cfg.psm}"
    if whitelist:
        config += f' -c tessedit_char_whitelist="{cfg.whitelist}"'
    try:
        return pytesseract.image_to_string(img, lang=cfg.lang, config=config)
    except pytesseract.TesseractNotFoundError as exc:
        logger.error(f"Tesseract no encontrado: {exc}")
        raise


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