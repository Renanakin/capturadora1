"""Esquemas Pydantic para configuración externa (Fase 1)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class PathsConfig(BaseModel):
    input_dir: Path = Path("documentos_ingresados")
    output_dir: Path = Path("output")
    quarantine_dir: Path = Path("quarantine")
    tesseract_cmd: Path = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
    tessdata_prefix: Path = Path("C:/Users/Tranquilidad/.tessdata")


class HsvRange(BaseModel):
    lower1: list[int] = Field(default_factory=lambda: [0, 70, 50])
    upper1: list[int] = Field(default_factory=lambda: [10, 255, 255])
    lower2: list[int] = Field(default_factory=lambda: [170, 70, 50])
    upper2: list[int] = Field(default_factory=lambda: [180, 255, 255])
    min_area: int = 5000
    aspect_ratio: list[float] = Field(default_factory=lambda: [1.5, 3.5])
    padding: int = 10


class OcrConfig(BaseModel):
    lang: str = "spa"
    psm: int = 6
    whitelist: str = "0123456789Kk.-RUTN° "
    dpi: int = 300


class ExcelConfig(BaseModel):
    template_columns: list[str] = Field(
        default_factory=lambda: [
            "Mes",
            "Fecha",
            "Nro Boleta Factura",
            "PROVEEDOR",
            "RUT",
            "Total",
            "Descripción del gasto",
            "Observaciones",
        ]
    )
    sheet_procesados: str = "Procesados"
    sheet_revision: str = "Revisión Manual"
    freeze_header: bool = True


class Settings(BaseModel):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    hsv_red: HsvRange = Field(default_factory=HsvRange)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    excel: ExcelConfig = Field(default_factory=ExcelConfig)

    @field_validator("hsv_red")
    @classmethod
    def _hsv_components_in_range(cls, v: HsvRange) -> HsvRange:
        for name in ("lower1", "upper1", "lower2", "upper2"):
            comp = getattr(v, name)
            if len(comp) != 3:
                raise ValueError(f"hsv_red.{name} debe tener 3 componentes H,S,V")
            h, s, x = comp
            if not (0 <= h <= 179):
                raise ValueError(f"hsv_red.{name}[0] (Hue) fuera de rango 0-179: {h}")
            if not (0 <= s <= 255 and 0 <= x <= 255):
                raise ValueError(f"hsv_red.{name} S/V fuera de rango 0-255")
        if v.min_area <= 0:
            raise ValueError("hsv_red.min_area debe ser > 0")
        return v