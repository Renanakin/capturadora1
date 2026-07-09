"""Entry-point multi-modo: api, worker, cli.

Uso:
  python -m ocr_tributario api               # arranca FastAPI en :8000
  python -m ocr_tributario worker            # arranca worker arq
  python -m ocr_tributario                   # modo CLI batch (default)
  python -m ocr_tributario --help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr_tributario",
        description="CapturadorM3 - OCR Tributario Chileno (CLI + API + Worker)",
    )
    sub = parser.add_subparsers(dest="mode", help="Modo de ejecución")

    # API server
    api_p = sub.add_parser("api", help="Arrancar API FastAPI")
    api_p.add_argument("--host", default="127.0.0.1")
    api_p.add_argument("--port", type=int, default=8000)
    api_p.add_argument("--reload", action="store_true")

    # Worker
    wrk_p = sub.add_parser("worker", help="Arrancar worker arq (procesa cola)")
    wrk_p.add_argument("--max-jobs", type=int, default=2)

    # CLI batch (default)
    cli_p = sub.add_parser("cli", help="Modo batch CLI")
    cli_p.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    cli_p.add_argument("--input", type=Path, default=None)
    cli_p.add_argument("--output", type=Path, default=None)
    cli_p.add_argument("--verbose", "-v", action="store_true")

    return parser


def _version() -> str:
    from ocr_tributario import __version__
    return __version__


def _run_api(args: argparse.Namespace) -> int:
    import uvicorn
    uvicorn.run(
        "ocr_tributario.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _run_worker(args: argparse.Namespace) -> int:
    import asyncio
    from arq import run_worker

    # Monkey-patch max_jobs si fue pasado
    from ocr_tributario.workers import WorkerSettings
    WorkerSettings.max_jobs = args.max_jobs

    asyncio.run(run_worker(WorkerSettings))
    return 0


def _run_cli(args: argparse.Namespace) -> int:
    from loguru import logger

    from ocr_tributario.config.loader import load_settings
    from ocr_tributario.exporters.excel_writer import export_records
    from ocr_tributario.orchestrator.pipeline import process_directory
    from ocr_tributario.utils.logging import setup_logging

    setup_logging(verbose=args.verbose)
    settings = load_settings()
    input_dir = args.input or Path(settings.paths.input_dir)
    logger.info(f"CapturadorM3 v{_version()}")
    logger.info(f"Input:  {input_dir}")

    if not input_dir.exists():
        logger.error(f"La carpeta de entrada no existe: {input_dir}")
        return 2

    report = process_directory(input_dir=input_dir, settings=settings)
    logger.info(f"Procesados={report.ok} OK · {report.quarantine} quarantine · {report.failed} failed")

    if report.records:
        written = export_records(report.records, output_path=args.output, settings=settings)
        logger.success(f"Excel escrito en {written}")
    else:
        logger.warning("No hay registros para exportar.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()

    # Si no se pasa subcomando, default = cli
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0] not in {"api", "worker", "cli", "--help", "-h", "--version"}:
        # Default CLI con sus propios args
        argv = ["cli"] + list(argv)

    args = parser.parse_args(argv)

    if args.mode == "api":
        return _run_api(args)
    if args.mode == "worker":
        return _run_worker(args)
    if args.mode == "cli":
        return _run_cli(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())