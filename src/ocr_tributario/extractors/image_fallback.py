"""Fallback: PDF escaneado -> imagen -> OCR (Fase 5.2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from loguru import logger

from ocr_tributario.config.schema import OcrConfig
from ocr_tributario.extractors.ocr_tesseract import configure_tesseract, ocr_array
from ocr_tributario.preprocessing.hsv_segmenter import extract_sii_red_box
from ocr_tributario.preprocessing.opencv_pipeline import preprocess_image
from ocr_tributario.config.schema import HsvRange


def render_pdf_to_images(
    pdf_path: Path, dpi: int = 300
) -> list[np.ndarray]:
    """Renderiza cada página del PDF como imagen BGR (numpy)."""
    import cv2

    pdf = pdfium.PdfDocument(str(pdf_path))
    images: list[np.ndarray] = []
    scale = dpi / 72.0
    for i in range(len(pdf)):
        page = pdf[i]
        pil_img = page.render(scale=scale).to_pil()
        rgb = np.array(pil_img)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        images.append(bgr)
    return images


def extract_pdf_image_fallback(
    pdf_path: Path,
    hsv_cfg: HsvRange,
    ocr_cfg: OcrConfig,
    tesseract_cmd: Path,
    tessdata_prefix: Path,
) -> dict[str, str]:
    """Renderiza PDF, intenta aislar recuadro SII, hace OCR sobre la mejor ROI."""
    configure_tesseract(tesseract_cmd, tessdata_prefix)

    images = render_pdf_to_images(pdf_path, dpi=ocr_cfg.dpi)
    if not images:
        return {"raw_text": "", "source": "empty"}

    full_text_chunks: list[str] = []
    for img in images:
        # Intentar recortar el recuadro rojo SII
        boxed = extract_sii_red_box(img, hsv_cfg)
        if boxed is not None:
            crop, _ = boxed
            logger.debug(f"Recuadro SII detectado en {pdf_path.name}")
            target = crop
        else:
            logger.debug(f"Sin recuadro SII, usando página completa ({pdf_path.name})")
            target = img

        pre = preprocess_image(target)
        text = ocr_array(pre, ocr_cfg, whitelist=True)
        full_text_chunks.append(text)

    return {"raw_text": "\n".join(full_text_chunks), "source": "pdf_image"}