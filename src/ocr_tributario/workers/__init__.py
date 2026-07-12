"""Worker arq para procesamiento asíncrono de jobs OCR."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from arq.connections import RedisSettings
from loguru import logger

from ocr_tributario.config.loader import load_settings
from ocr_tributario.db import (
    add_job_record,
    create_job,
    init_db,
    update_job,
)
from ocr_tributario.exporters.excel_writer import export_records
from ocr_tributario.models.invoice import InvoiceRecord
from ocr_tributario.orchestrator.pipeline import process_one


REDIS_HOST = "localhost"
REDIS_PORT = 6379


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("Worker arq iniciando...")
    await init_db()
    logger.info("DB inicializada")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("Worker arq detenido")


async def process_job(
    ctx,  # inyectado por arq en runtime
    files: list[str],
    job_id: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Procesa una lista de archivos en background.

    Args:
        files: rutas absolutas a los archivos
        job_id: ID del job para tracking (opcional)
        output_path: ruta del Excel de salida (opcional)

    Returns:
        dict con estadísticas y path del Excel generado
    """
    settings = load_settings()
    job_id = job_id or uuid.uuid4().hex[:12]
    logger.info(f"Job {job_id}: {len(files)} archivos")

    if not job_id:
        job_id = uuid.uuid4().hex[:12]

    # Crear o actualizar job en DB
    import sqlite3
    try:
        await create_job(job_id, total_files=len(files), metadata={"files": files, "output_path": output_path})
    except sqlite3.IntegrityError:
        pass  # El job ya fue creado por la API
    await update_job(job_id, status="processing")

    records: list[InvoiceRecord] = []
    processed = 0
    failed = 0

    for fpath in files:
        p = Path(fpath)
        if not p.exists():
            logger.warning(f"Archivo no existe, se omite: {fpath}")
            continue
        try:
            rec = process_one(p, settings)
        except Exception as exc:
            logger.exception(f"Error procesando {fpath}")
            rec = InvoiceRecord(
                archivo_origen=p.name,
                estado="REJECTED",
                motivo_revision=f"Excepción: {type(exc).__name__}: {exc}",
            )

        records.append(rec)
        if rec.estado == "OK":
            processed += 1
        elif rec.estado == "QUARANTINE":
            processed += 1
        else:
            failed += 1

        await add_job_record(
            job_id,
            rec.archivo_origen,
            estado=rec.estado,
            rut=rec.rut,
            fecha=rec.fecha,
            total=rec.total,
            proveedor=rec.proveedor,
            folio=rec.nro_documento,
            doc_type=str(rec.ruta_extraccion),
            ocr_engine=rec.ruta_extraccion,
            ocr_avg_score=None,
            missing_fields=[],
            raw_text=getattr(rec, "raw_text", None),
        )
        await update_job(job_id, processed=processed, failed=failed)

    # Exportar Excel
    written: str | None = None
    try:
        if records:
            out = Path(output_path) if output_path else Path(settings.paths.output_dir) / f"Rendicion_Job_{job_id}.xlsx"
            written = str(export_records(records, output_path=out, settings=settings))
    except Exception as exc:
        logger.exception(f"Error exportando Excel del job {job_id}")
        await update_job(job_id, status="failed", error=f"Excel export failed: {exc}")
        return {"job_id": job_id, "error": str(exc)}

    await update_job(
        job_id,
        status="done",
        processed=processed,
        failed=failed,
        output_path=written,
    )
    logger.info(f"Job {job_id} terminado: {processed} OK, {failed} failed → {written}")
    return {
        "job_id": job_id,
        "processed": processed,
        "failed": failed,
        "output_path": written,
    }


class WorkerSettings:
    """Configuración del worker arq."""
    functions = [process_job]
    redis_settings = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
    on_startup = startup
    on_shutdown = shutdown
    keep_result = 60 * 60  # 1 hora
    max_jobs = 2
    poll_delay = 0.5
    queue_name = "ocr-jobs"