"""Segmentación HSV del recuadro rojo SII (Fase 4)."""

from __future__ import annotations

import numpy as np
import cv2

from ocr_tributario.config.schema import HsvRange


def _build_masks(hsv: np.ndarray, cfg: HsvRange) -> np.ndarray:
    m1 = cv2.inRange(hsv, np.array(cfg.lower1, dtype=np.uint8), np.array(cfg.upper1, dtype=np.uint8))
    m2 = cv2.inRange(hsv, np.array(cfg.lower2, dtype=np.uint8), np.array(cfg.upper2, dtype=np.uint8))
    mask = cv2.add(m1, m2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    return cv2.dilate(mask, kernel, iterations=1)


def extract_sii_red_box(
    img_bgr: np.ndarray, cfg: HsvRange
) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    """Aísla el recuadro rojo del SII. Retorna (crop, (x, y, w, h)) o None."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = _build_masks(hsv, cfg)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best: tuple[int, tuple[int, int, int, int]] | None = None
    min_ar, max_ar = cfg.aspect_ratio
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < cfg.min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0 or w == 0:
            continue
        ar = w / float(h)
        if not (min_ar <= ar <= max_ar):
            continue
        if best is None or area > best[0]:
            best = (area, (x, y, w, h))

    if best is None:
        return None

    _, (x, y, w, h) = best
    pad = cfg.padding
    H, W = img_bgr.shape[:2]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(W, x + w + pad)
    y1 = min(H, y + h + pad)

    crop = img_bgr[y0:y1, x0:x1].copy()
    return crop, (x0, y0, x1 - x0, y1 - y0)