"""Motor OCR principal: PaddleOCR.

Devuelve líneas con coordenadas (box), texto y confianza.
Es la recomendación principal para documentos chilenos estructurados.
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
    engine: str  # 'paddle' | 'tesseract' | 'multi'

    def __repr__(self) -> str:
        return f"OCRResult(engine={self.engine!r}, lines={len(self.lines)}, avg_score={self.avg_score:.3f})"


class OCRPaddle:
    """Wrapper de PaddleOCR con caché de instancia y API uniforme."""

    _instances: dict[str, "OCRPaddle"] = {}
    _lock = Lock()

    def __init__(self, lang: str = 'es', use_angle_cls: bool = True) -> None:
        with OCRPaddle._lock:
            key = f"lang={lang}|angle={use_angle_cls}"
            if key in OCRPaddle._instances:
                # Reusar instancia cacheada
                cached = OCRPaddle._instances[key]
                self.__dict__.update(cached.__dict__)
                return

            warnings.filterwarnings("ignore")
            # Lazy import
            from paddleocr import PaddleOCR
            logger.info(f"Inicializando PaddleOCR (lang={lang}, angle={use_angle_cls})...")
            self._reader = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang, enable_mkldnn=False)
            self.lang = lang
            OCRPaddle._instances[key] = self
            logger.info("PaddleOCR inicializado OK")

    def read(
        self,
        image_path_or_array: Path | str | np.ndarray,
    ) -> OCRResult:
        """Lee una imagen y devuelve OCRResult con líneas + score promedio."""
        if isinstance(image_path_or_array, np.ndarray):
            arr = image_path_or_array
            if len(arr.shape) == 2:
                import cv2
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        else:
            arr = str(image_path_or_array)

        # result es una lista de páginas. Usualmente es 1 página para una imagen
        raw_result = self._reader.ocr(arr)
        lines: list[OCRLine] = []
        
        if raw_result and raw_result[0]:
            for page in raw_result:
                if page is None:
                    continue
                # PaddleOCR 3.x/PaddleX returns a dict-like object
                if hasattr(page, "get") and "rec_texts" in page:
                    polys = page.get("dt_polys") or page.get("rec_polys", [])
                    texts = page.get("rec_texts", [])
                    scores = page.get("rec_scores", [])
                    items = zip(polys, zip(texts, scores))
                elif hasattr(page, "get") and "res" in page:
                    items = page["res"]
                elif isinstance(page, list) and len(page) > 0 and isinstance(page[0], dict):
                    items = []
                    for it in page:
                        items.append((it["poly"], (it["text"], it["score"])))
                else:
                    items = page
                
                try:
                    for item in items:
                        if isinstance(item, str):
                            continue
                        box, (text, score) = item
                        lines.append(OCRLine(
                            text=str(text).strip(),
                            score=float(score),
                            box=[(int(p[0]), int(p[1])) for p in box],
                        ))
                except Exception as e:
                    logger.warning(f"Error parsing PaddleOCR output: {e}")
                    
        avg_score = (sum(l.score for l in lines) / len(lines)) if lines else 0.0
        full_text = "\n".join(l.text for l in lines)
        return OCRResult(lines=lines, full_text=full_text, avg_score=avg_score, engine="paddle")

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
            engine="paddle",
        )
