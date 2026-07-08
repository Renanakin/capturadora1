"""Smoke test del segmentador HSV (sin dependencias externas reales)."""

from __future__ import annotations

import numpy as np
import pytest

from ocr_tributario.config.schema import HsvRange
from ocr_tributario.preprocessing.hsv_segmenter import extract_sii_red_box


def _make_red_box_image(w: int = 600, h: int = 400) -> np.ndarray:
    """Crea una imagen sintética con un rectángulo rojo central estilo SII."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)  # fondo blanco
    # Rectángulo de 300x150 -> aspect_ratio=2.0 (dentro de [1.5, 3.5])
    x0, y0, x1, y1 = 150, 120, 450, 270
    img[y0:y1, x0:x1] = (40, 40, 200)  # rojo en BGR
    return img


def test_segmenter_detects_box():
    img = _make_red_box_image()
    cfg = HsvRange()
    result = extract_sii_red_box(img, cfg)
    assert result is not None
    crop, bbox = result
    assert crop.shape[0] > 0 and crop.shape[1] > 0
    x, y, w, h = bbox
    assert w > 100 and h > 30


def test_segmenter_returns_none_on_white():
    img = np.full((300, 600, 3), 255, dtype=np.uint8)
    cfg = HsvRange()
    assert extract_sii_red_box(img, cfg) is None