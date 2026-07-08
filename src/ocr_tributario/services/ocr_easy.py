"""Motor OCR principal: EasyOCR (neuronal, basado en PyTorch).

Devuelve líneas con coordenadas (box), texto y confianza. Es significativamente
mejor que Tesseract en español para facturas/boletas chilenas.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
from loguru import logger


@dataclass
class OCRLine:
    """Una línea detectada por OCR con coordenadas y confianza."""
    text: str
    score: float
    box: list[tuple[int, int]]  # 4 puntos (x,y)


@dataclass
class OCRResult:
    """Resultado completo de un OCR (una imagen)."""
    lines: list[OCRLine]
    full_text: str
    avg_score: float
    engine: str  # 'easy' | 'tesseract' | 'multi'

    def __repr__(self) -> str:
        return f"OCRResult(engine={self.engine!r}, lines={len(self.lines)}, avg_score={self.avg_score:.3f})"


class OCREasy:
    """Wrapper de EasyOCR con caché de instancia y API uniforme."""

    _instances: dict[str, "OCREasy"] = {}
    _lock = Lock()

    def __init__(self, langs: tuple[str, ...] = ("es",), gpu: bool = False) -> None:
        with OCREasy._lock:
            key = f"{','.join(langs)}|gpu={gpu}"
            if key in OCREasy._instances:
                # Reusar instancia cacheada
                cached = OCREasy._instances[key]
                self.__dict__.update(cached.__dict__)
                return

            warnings.filterwarnings("ignore")
            # Lazy import (easyocr es pesado)
            import easyocr
            logger.info(f"Inicializando EasyOCR (langs={langs}, gpu={gpu})...")
            self._reader = easyocr.Reader(list(langs), gpu=gpu, verbose=False)
            self.langs = langs
            self.gpu = gpu
            OCREasy._instances[key] = self
            logger.info("EasyOCR inicializado OK")

    def read(
        self,
        image_path_or_array: Path | str | np.ndarray,
        detail: int = 1,
        paragraph: bool = False,
    ) -> OCRResult:
        """Lee una imagen y devuelve OCRResult con líneas + score promedio."""
        if isinstance(image_path_or_array, np.ndarray):
            arr = image_path_or_array
        else:
            arr = str(image_path_or_array)

        raw = self._reader.readtext(arr, detail=detail, paragraph=paragraph)
        lines: list[OCRLine] = []
        for item in raw:
            box, text, score = item
            lines.append(OCRLine(
                text=str(text).strip(),
                score=float(score),
                box=[(int(p[0]), int(p[1])) for p in box],
            ))
        avg_score = (sum(l.score for l in lines) / len(lines)) if lines else 0.0
        full_text = "\n".join(l.text for l in lines)
        return OCRResult(lines=lines, full_text=full_text, avg_score=avg_score, engine="easy")

    def read_with_confidence_threshold(
        self,
        image_path_or_array: Path | str | np.ndarray,
        min_score: float = 0.3,
    ) -> OCRResult:
        """Lee y descarta líneas con confianza muy baja (ruido)."""
        result = self.read(image_path_or_array)
        filtered = [l for l in result.lines if l.score >= min_score]
        avg = (sum(l.score for l in filtered) / len(filtered)) if filtered else 0.0
        return OCRResult(
            lines=filtered,
            full_text="\n".join(l.text for l in filtered),
            avg_score=avg,
            engine="easy",
        )