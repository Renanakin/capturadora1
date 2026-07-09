from dataclasses import dataclass
from typing import Literal

@dataclass
class CedulaRecord:
    archivo_origen: str
    rut: str | None = None
    nombres: str | None = None
    apellidos: str | None = None
    fecha_nacimiento: str | None = None
    numero_documento: str | None = None
    estado: Literal["OK", "QUARANTINE", "REJECTED"] = "QUARANTINE"
    motivo_revision: str | None = None
    ocr_engine: str | None = None
    ocr_avg_score: float | None = None
    ruta_extraccion: str | None = None

    @property
    def completeness(self) -> float:
        fields = [self.rut, self.nombres, self.apellidos, self.numero_documento]
        filled = sum(1 for f in fields if f)
        return filled / len(fields)

    def is_valid_for_excel(self) -> bool:
        return bool(self.rut and self.numero_documento)
