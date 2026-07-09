"""Schemas HTTP (request/response) para FastAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Union

from pydantic import BaseModel, Field

from ocr_tributario.schemas.ocr import DTEResponseSchema, CedulaResponseSchema


class UploadResponse(BaseModel):
    """Respuesta del endpoint /upload (procesamiento sincrónico)."""
    job_id: str
    archivo: str
    result: Union[DTEResponseSchema, CedulaResponseSchema]


class BatchUploadResponse(BaseModel):
    """Respuesta del endpoint /upload-batch (múltiples archivos, sincrónico)."""
    job_id: str
    total: int
    processed: int
    failed: int
    records: list[Union[DTEResponseSchema, CedulaResponseSchema]]


class JobEnqueueResponse(BaseModel):
    """Respuesta al encolar un job para procesamiento asíncrono."""
    job_id: str
    status: str
    total_files: int
    message: str = "Job encolado. Use GET /jobs/{id} para ver el estado."


class JobStatus(BaseModel):
    id: str
    status: str
    total_files: int
    processed: int
    failed: int
    output_path: str | None = None
    created_at: str
    updated_at: str
    error: str | None = None


class JobDetail(JobStatus):
    records: list[dict[str, Any]] = Field(default_factory=list)


class RutValidationRequest(BaseModel):
    rut: str


class RutValidationResponse(BaseModel):
    rut_input: str
    canonico: str | None
    valido: bool
    dv_calculado: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    redis: bool
    db: bool
    timestamp: datetime


class ErrorResponse(BaseModel):
    detail: str