"""Motor OCR fallback: Tesseract.

Usado cuando EasyOCR no está disponible o como segunda opinión en campos
críticos. Conserva la API uniforme (OCRResult, OCRLine).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytesseract
from loguru import logger
from PIL import Image

from ocr_tributario.config.schema import OcrConfig
from ocr_tributario.services.ocr_paddle import OCRLine, OCRResult


def _build_tesseract_config(cfg: OcrConfig, psm: int | None = None) -> str:
    return f"--psm {psm if psm is not None else cfg.psm}"


class OCRTesseract:
    """Wrapper de Tesseract."""

    def __init__(self, tesseract_cmd: str | Path, tessdata_prefix: str | Path) -> None:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
        import os
        os.environ["TESSDATA_PREFIX"] = str(tessdata_prefix)
        self.tesseract_cmd = str(tesseract_cmd)
        self.tessdata_prefix = str(tessdata_prefix)

    def read(self, image_path_or_array: Path | str | np.ndarray, cfg: OcrConfig) -> OCRResult:
        """Lee una imagen y devuelve OCRResult con líneas + score promedio."""
        if isinstance(image_path_or_array, np.ndarray):
            arr = image_path_or_array
            if len(arr.shape) == 3:
                from cv2 import cv2
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(arr)
        else:
            img = Image.open(str(image_path_or_array))

        config = _build_tesseract_config(cfg)

        # Texto plano
        try:
            text = pytesseract.image_to_string(img, lang=cfg.lang, config=config)
        except pytesseract.TesseractNotFoundError as exc:
            logger.error(f"Tesseract no encontrado: {exc}")
            raise

        # image_to_data para score y boxes
        try:
            data = pytesseract.image_to_data(
                img,
                lang=cfg.lang,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
            lines: list[OCRLine] = []
            for i, (txt, conf, x, y, w, h) in enumerate(
                zip(data["text"], data["conf"], data["left"], data["top"], data["width"], data["height"])
            ):
                t = (txt or "").strip()
                if not t:
                    continue
                try:
                    score = float(conf) / 100.0
                except (ValueError, TypeError):
                    score = 0.5
                if score < 0:
                    score = 0.5
                box = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                lines.append(OCRLine(text=t, score=score, box=box))
            avg_score = (sum(l.score for l in lines) / len(lines)) if lines else 0.0
        except Exception as exc:
            logger.warning(f"image_to_data falló: {exc}; usando texto plano sin score")
            lines = [OCRLine(text=line, score=0.5, box=[(0, 0), (100, 0), (100, 20), (0, 20)])
                     for line in text.splitlines() if line.strip()]
            avg_score = 0.5

        return OCRResult(lines=lines, full_text=text, avg_score=avg_score, engine="tesseract")

    def read_multi_psm(
        self,
        image_path_or_array: Path | str | np.ndarray,
        cfg: OcrConfig,
        psms: tuple[int, ...] = (3, 4, 6, 11),
    ) -> OCRResult:
        """Multi-PSM: elige el que dé más campos extraíbles."""
        from ocr_tributario.validators.regex_patterns import (
            _RUT_INLINE,
            extract_date,
            extract_total,
        )

        if isinstance(image_path_or_array, np.ndarray):
            arr = image_path_or_array
            if len(arr.shape) == 3:
                import cv2
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(arr)
        else:
            img = Image.open(str(image_path_or_array))

        best: tuple[int, OCRResult] | None = None
        for psm in psms:
            config = f"--psm {psm}"
            try:
                text = pytesseract.image_to_string(img, lang=cfg.lang, config=config)
            except Exception:
                continue
            score = 0
            if _RUT_INLINE.search(text):
                score += 5
            if extract_date(text):
                score += 3
            if extract_total(text):
                score += 4
            if len(text.strip()) > 50:
                score += 1
            result = OCRResult(
                lines=[OCRLine(text=t, score=0.5, box=[(0, 0)]) for t in text.splitlines() if t.strip()],
                full_text=text,
                avg_score=0.5,
                engine=f"tesseract-psm{psm}",
            )
            if best is None or score > best[0]:
                best = (score, result)

        if best is None:
            return OCRResult(lines=[], full_text="", avg_score=0.0, engine="tesseract-failed")
        return best[1]