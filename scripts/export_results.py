"""Corre el pipeline sobre `documentos_ingresados` y exporta Excel + CSV
usando el formato preestablecido (9 columnas de `excel.template_columns`).

Uso:
    python -m scripts.export_results
    python -m scripts.export_results --input otra_carpeta
    python -m scripts.export_results --xlsx output/Rendicion.xlsx --csv output/Rendicion.csv
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = sys.stdout

from ocr_tributario.config.loader import load_settings
from ocr_tributario.exporters.csv_writer import export_csv
from ocr_tributario.exporters.excel_writer import export_records
from ocr_tributario.orchestrator.pipeline import process_directory


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta Excel + CSV preestablecido")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("documentos_ingresados"),
        help="Carpeta con documentos a procesar",
    )
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=Path("output/Rendicion_Gastos_OCR.xlsx"),
        help="Ruta del Excel de salida",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("output/Rendicion_Gastos_OCR.csv"),
        help="Ruta del CSV de salida (solo registros OK)",
    )
    parser.add_argument(
        "--csv-revision",
        type=Path,
        default=Path("output/Rendicion_Gastos_OCR_revision.csv"),
        help="Ruta del CSV con QUARANTINE/REJECTED (estado + motivo + 9 cols)",
    )
    args = parser.parse_args()

    settings = load_settings()
    print(f"Procesando: {args.input}")
    report = process_directory(input_dir=args.input, settings=settings)
    print(f"  OK={report.ok}  QUARANTINE={report.quarantine}  REJECTED={report.failed}")
    print(f"  Total={len(report.records)}")

    if not report.records:
        print("Sin registros para exportar")
        return 1

    # Excel: 2 hojas (Procesados + Revisión Manual)
    xlsx_path = export_records(
        report.records,
        output_path=args.xlsx,
        settings=settings,
    )
    print(f"Excel escrito: {xlsx_path}")

    # CSV: solo registros OK con las 9 columnas preestablecidas
    csv_path = export_csv(
        report.records,
        output_path=args.csv,
        settings=settings,
        include_quarantine=False,
    )
    print(f"CSV (OK) escrito: {csv_path}")

    # CSV adicional: revisión manual (estado + motivo + 9 cols)
    csv_rev_path = export_csv(
        report.records,
        output_path=args.csv_revision,
        settings=settings,
        include_quarantine=True,
    )
    print(f"CSV (revisión) escrito: {csv_rev_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
