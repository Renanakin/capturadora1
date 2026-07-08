"""Pipeline OpenCV para imágenes (Fase 3).

Pasos:
1. Carga BGR.
2. Escala de grises.
3. Upsample si es muy pequeña.
4. CLAHE (contraste adaptativo) para fotos con luz desigual.
5. Filtro bilateral (preserva bordes).
6. Sharpening suave.
7. Deskew (rotación por ángulo dominante).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_image(path: Path) -> np.ndarray:
    """Lee imagen en BGR. Soporta los formatos habituales de OpenCV."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen: {path}")
    return img


def to_grayscale(img_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def upsample_if_small(gray: np.ndarray, min_dim: int = 800) -> np.ndarray:
    """Si la dimensión mayor es < min_dim, escala hasta 1500 con cúbico."""
    h, w = gray.shape
    if max(h, w) >= min_dim:
        return gray
    scale = 1500 / float(max(h, w))
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


def apply_clahe(gray: np.ndarray, clip_limit: float = 2.5, tile: tuple[int, int] = (8, 8)) -> np.ndarray:
    """CLAHE: contraste adaptativo. Útil para fotos con luz desigual."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile)
    return clahe.apply(gray)


def bilateral_denoise(gray: np.ndarray, d: int = 9, sigma: float = 75.0) -> np.ndarray:
    return cv2.bilateralFilter(gray, d, sigma, sigma)


def sharpen(gray: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """Unsharp mask: resta versión borrosa de la imagen para resaltar bordes."""
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0)
    return cv2.addWeighted(gray, 1 + amount, blurred, -amount, 0)


def adaptive_threshold(gray: np.ndarray, block_size: int = 31, c: int = 10) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c
    )


def estimate_skew_angle(binary: np.ndarray) -> float:
    """Estima ángulo de rotación dominante en grados."""
    coords = np.column_stack(np.where(binary < 128))
    if len(coords) < 100:
        return 0.0
    rect = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    if angle > 45:
        angle = angle - 90
    return float(angle)


def deskew(gray: np.ndarray, angle: float | None = None) -> np.ndarray:
    """Rota la imagen para corregir el ángulo estimado (o uno provisto)."""
    if angle is None:
        binary = adaptive_threshold(gray)
        angle = estimate_skew_angle(binary)
    if abs(angle) < 0.2:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def preprocess_image(img_bgr: np.ndarray, sharpen_amt: float = 0.8) -> np.ndarray:
    """Pipeline completo: gray -> upsample -> CLAHE -> denoise -> sharpen -> deskew.

    Devuelve imagen en escala de grises lista para OCR (no binarizada: tesseract
    funciona mejor con escala de grises que con threshold duro en imágenes
    con sombras).
    """
    gray = to_grayscale(img_bgr)
    gray = upsample_if_small(gray, min_dim=800)
    gray = apply_clahe(gray)
    gray = bilateral_denoise(gray)
    if sharpen_amt > 0:
        gray = sharpen(gray, amount=sharpen_amt)
    gray = deskew(gray)
    return gray