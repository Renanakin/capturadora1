"""Modelo de datos principal: InvoiceRecord (Fase 7)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

EstadoDocumento = Literal["OK", "QUARANTINE", "REJECTED"]


@dataclass
class InvoiceRecord:
    archivo_origen: str
    mes: str | None = None
    fecha: str | None = None  # YYYY-MM-DD
    nro_documento: int | None = None
    proveedor: str | None = None
    rut: str | None = None
    total: int | None = None
    descripcion: str | None = None
    observaciones: str | None = None
    estado: EstadoDocumento = "QUARANTINE"
    motivo_revision: str | None = None
    ruta_extraccion: str | None = None
    raw_text: str | None = None
    doc_type: str | None = None
    ocr_engine: str | None = None
    ocr_avg_score: float | None = None
    completeness: float | None = None
    timestamp_proceso: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp_proceso"] = self.timestamp_proceso.isoformat(timespec="seconds")
        return d

    def is_complete(self) -> bool:
        return all([self.fecha, self.nro_documento, self.proveedor, self.rut, self.total])

    def is_valid_for_excel(self) -> bool:
        """Campos mínimos para subir a la planilla sin pasar por revisión."""
        return bool(self.fecha and self.rut and self.total is not None)