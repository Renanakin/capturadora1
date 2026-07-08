"""Pipeline OpenCV para imágenes (Fase 3).

Pasos:
1. Carga BGR.
2. Escala de grises.
3. Filtro bilateral (preserva bordes).
4. Umbralizado adaptativo gaussiano.
5. Deskew (rotación por ángulo dominante).
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


def bilateral_denoise(gray: np.ndarray, d: int = 9, sigma: float = 75.0) -> np.ndarray:
    return cv2.bilateralFilter(gray, d, sigma, sigma)


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


def preprocess_image(img_bgr: np.ndarray) -> np.ndarray:
    """Pipeline completo: gray -> denoise -> deskew -> binarización suave."""
    gray = to_grayscale(img_bgr)

    # Upsample si la imagen es muy pequeña (mejora OCR en fotos chicas)
    h, w = gray.shape
    if max(h, w) < 800:
        scale = 1500 / float(max(h, w))
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    denoised = bilateral_denoise(gray)
    straightened = deskew(denoised)
    return straightened