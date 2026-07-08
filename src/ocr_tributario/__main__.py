"""Entry-point: python -m ocr_tributario [--input DIR] [--output FILE]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from ocr_tributario import __version__
from ocr_tributario.config.loader import load_settings
from ocr_tributario.exporters.excel_writer import export_records
from ocr_tributario.orchestrator.pipeline import process_directory
from ocr_tributario.utils.logging import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr_tributario",
        description="CapturadorM3 - extrae datos de boletas/facturas chilenas a Excel.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Carpeta con PDFs/imágenes a procesar (default: config.settings.yaml).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta del Excel de salida (default: output/Rendicion_Gastos_OCR_<YYYY-MM>.xlsx).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Logging en nivel DEBUG."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    setup_logging(verbose=args.verbose)
    settings = load_settings()

    input_dir = args.input or Path(settings.paths.input_dir)
    output_path = args.output or None  # el writer decide el nombre por defecto

    logger.info(f"CapturadorM3 v{__version__}")
    logger.info(f"Input:  {input_dir}")
    logger.info(f"Output: {output_path or '(auto: output/Rendicion_Gastos_OCR_<YYYY-MM>.xlsx)'}")

    if not input_dir.exists():
        logger.error(f"La carpeta de entrada no existe: {input_dir}")
        return 2

    report = process_directory(input_dir=input_dir, settings=settings)

    logger.info(
        f"Procesados={report.ok} OK · {report.quarantine} quarantine · {report.failed} failed"
    )

    if report.records:
        written = export_records(report.records, output_path=output_path, settings=settings)
        logger.success(f"Excel escrito en {written}")
    else:
        logger.warning("No hay registros para exportar.")

    return 0


if __name__ == "__main__":
    sys.exit(main())