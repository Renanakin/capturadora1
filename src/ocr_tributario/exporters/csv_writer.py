"""Exportador CSV (Fase 9 + CSV complementario).

Genera un CSV con el mismo formato preestablecido (9 columnas) que el
Excel de rendición. Pensado para integraciones con planillas externas
o ERPs que no soporten xlsx.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from loguru import logger

from ocr_tributario.config.schema import Settings
from ocr_tributario.models.invoice import InvoiceRecord


# Mapeo de columna (settings.yaml) → atributo del InvoiceRecord
_COL_MAP: dict[str, str] = {
    "Archivo": "archivo_origen",
    "Mes": "mes",
    "Fecha": "fecha",
    "Nro Boleta Factura": "nro_documento",
    "PROVEEDOR": "proveedor",
    "RUT": "rut",
    "Total": "total",
    "Descripción del gasto": "descripcion",
    "Observaciones": "observaciones",
}


def _row_for(record: InvoiceRecord, columns: list[str]) -> list:
    out: list = []
    for col in columns:
        attr = _COL_MAP.get(col)
        if attr is None:
            out.append("")
            continue
        val = getattr(record, attr, None)
        if val is None:
            out.append("")
        else:
            out.append(val)
    return out


def _row_for_revision(record: InvoiceRecord) -> list:
    """Fila adicional para hoja/CSV de revisión: misma estructura que
    Procesados pero con estado + motivo al final."""
    return [
        record.archivo_origen,
        record.estado,
        record.motivo_revision or "",
        record.mes or "",
        record.fecha or "",
        record.nro_documento if record.nro_documento is not None else "",
        record.proveedor or "",
        record.rut or "",
        record.total if record.total is not None else "",
    ]


def _to_native(val):
    """CSV no soporta nativamente None / int con miles. Aplica saneado."""
    if val is None:
        return ""
    if isinstance(val, int):
        # Sin separadores de miles: el Excel ya da formato al cargar
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat(timespec="seconds")
    return val


def export_csv(
    records: list[InvoiceRecord],
    output_path: Path,
    settings: Settings,
    *,
    include_quarantine: bool = False,
) -> Path:
    """Escribe el CSV de rendición con el formato preestablecido (9 columnas).

    Args:
        records: registros a exportar.
        output_path: ruta destino del CSV.
        settings: configuración (lee `excel.template_columns`).
        include_quarantine: si True, incluye registros en QUARANTINE/REJECTED
            con columna extra `estado` al inicio. Si False (default), exporta
            solo los registros OK con las 9 columnas preestablecidas.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = settings.excel.template_columns
    base = [_to_native(v) for v in (None,)]  # placeholder, no se usa

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        if include_quarantine:
            # Estructura extendida: estado + motivo + 9 columnas
            writer.writerow(["estado", "motivo_revision", *columns])
            for r in records:
                base_row = _row_for(r, columns)
                writer.writerow(
                    [_to_native(r.estado), _to_native(r.motivo_revision), *_row_for(r, columns)]
                )
        else:
            # Estructura estándar: 9 columnas preestablecidas (solo OK)
            writer.writerow(columns)
            for r in records:
                if r.estado != "OK":
                    continue
                writer.writerow([_to_native(v) for v in _row_for(r, columns)])

    n = sum(1 for r in records if r.estado == "OK")
    logger.info(f"CSV OK ({n} registros) -> {output_path}")
    return output_path
