"""Servicios OCR: motor principal, fallback, clasificador y parsers.

Arquitectura por capas (siguiendo el documento stack_ocr_chile_fastapi.md):
- preprocess: preprocesamiento de imágenes (OpenCV)
- ocr_easy: motor OCR neuronal principal (EasyOCR)
- ocr_tesseract: fallback OCR clásico (Tesseract)
- classify: clasificación de tipo de documento
- parse_dte: parser específico por tipo DTE
"""

from ocr_tributario.services.ocr_easy import OCREasy
from ocr_tributario.services.ocr_tesseract import OCRTesseract
from ocr_tributario.services.classify import classify_document
from ocr_tributario.services.parse_dte import parse_dte_fields