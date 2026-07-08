"""Exportador Excel (Fase 9)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ocr_tributario.config.schema import Settings
from ocr_tributario.models.invoice import InvoiceRecord

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="305496")


def _row_for(record: InvoiceRecord, columns: list[str]) -> list:
    mapping = {
        "Mes": record.mes or "",
        "Fecha": record.fecha or "",
        "Nro Boleta Factura": record.nro_documento or "",
        "PROVEEDOR": record.proveedor or "",
        "RUT": record.rut or "",
        "Total": record.total if record.total is not None else "",
        "Descripción del gasto": record.descripcion or "",
        "Observaciones": record.observaciones or "",
    }
    return [mapping.get(col, "") for col in columns]


def export_records(
    records: list[InvoiceRecord],
    output_path: Path | None,
    settings: Settings,
) -> Path:
    """Escribe el Excel de rendición con dos hojas: Procesados + Revisión Manual."""
    output_dir: Path = settings.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        period = datetime.now().strftime("%Y-%m")
        output_path = output_dir / f"Rendicion_Gastos_OCR_{period}.xlsx"

    wb = Workbook()
    ws_ok = wb.active
    ws_ok.title = settings.excel.sheet_procesados

    columns = settings.excel.template_columns
    ws_ok.append(columns)
    if settings.excel.freeze_header:
        ws_ok.freeze_panes = "A2"

    for cell in ws_ok[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")

    ok_records = [r for r in records if r.estado == "OK"]
    for rec in ok_records:
        ws_ok.append(_row_for(rec, columns))

    for i in range(1, len(columns) + 1):
        col_letter = get_column_letter(i)
        ws_ok.column_dimensions[col_letter].width = max(14, len(columns[i - 1]) + 4)

    # Hoja 2: revisión manual
    ws_rev = wb.create_sheet(settings.excel.sheet_revision)
    rev_columns = ["archivo_origen", "motivo_revision", "fecha", "nro_documento", "proveedor", "rut", "total"]
    ws_rev.append(rev_columns)
    if settings.excel.freeze_header:
        ws_rev.freeze_panes = "A2"
    for cell in ws_rev[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for rec in records:
        if rec.estado in ("QUARANTINE", "REJECTED"):
            ws_rev.append([
                rec.archivo_origen,
                rec.motivo_revision or "",
                rec.fecha or "",
                rec.nro_documento or "",
                rec.proveedor or "",
                rec.rut or "",
                rec.total if rec.total is not None else "",
            ])

    for i in range(1, len(rev_columns) + 1):
        col_letter = get_column_letter(i)
        ws_rev.column_dimensions[col_letter].width = 18

    wb.save(output_path)
    logger.info(f"Excel OK ({len(ok_records)} registros) -> {output_path}")
    return output_path