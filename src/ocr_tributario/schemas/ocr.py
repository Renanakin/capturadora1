"""Schemas Pydantic para OCR / DTE response."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ocr_tributario.services.classify import DocumentType


class OCRLineSchema(BaseModel):
    text: str
    score: float = Field(..., ge=0.0, le=1.0)
    box: list[list[int]] | None = None


class DTEResponseSchema(BaseModel):
    """Respuesta de OCR para un documento tributario."""

    archivo: str
    doc_type: DocumentType
    ocr_engine: str
    ocr_avg_score: float

    folio: int | None = None
    fecha_emision: date | None = None
    rut_emisor: str | None = None
    razon_social: str | None = None
    giro: str | None = None
    rut_receptor: str | None = None

    neto: int | None = None
    iva: int | None = None
    total: int | None = None
    exento: int | None = None

    completeness: float = 0.0
    missing: list[str] = []
    estado: str = "OK"
    motivo_revision: str | None = None


class CedulaResponseSchema(BaseModel):
    """Respuesta de OCR para una Cédula Chilena."""

    archivo: str
    doc_type: DocumentType = DocumentType.CEDULA
    ocr_engine: str
    ocr_avg_score: float

    rut: str | None = None
    nombres: str | None = None
    apellidos: str | None = None
    fecha_nacimiento: str | None = None
    numero_documento: str | None = None

    completeness: float = 0.0
    estado: str = "OK"
    motivo_revision: str | None = None