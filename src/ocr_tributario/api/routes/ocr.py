import uuid
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger

from ocr_tributario.api.schemas import BatchUploadResponse, JobEnqueueResponse, UploadResponse
from ocr_tributario.config.loader import load_settings
from ocr_tributario.db import add_job_record, create_job, update_job
from ocr_tributario.models.invoice import InvoiceRecord
from ocr_tributario.models.cedula import CedulaRecord
from ocr_tributario.orchestrator.pipeline import process_one
from ocr_tributario.schemas.ocr import DTEResponseSchema, CedulaResponseSchema
from ocr_tributario.services.classify import DocumentType

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _record_to_schema(rec: InvoiceRecord | CedulaRecord) -> DTEResponseSchema | CedulaResponseSchema:
    if isinstance(rec, CedulaRecord):
        return CedulaResponseSchema(
            archivo=rec.archivo_origen,
            ocr_engine=rec.ocr_engine or rec.ruta_extraccion or "unknown",
            ocr_avg_score=rec.ocr_avg_score or 0.0,
            rut=rec.rut,
            nombres=rec.nombres,
            apellidos=rec.apellidos,
            fecha_nacimiento=rec.fecha_nacimiento,
            numero_documento=rec.numero_documento,
            estado=rec.estado,
            motivo_revision=rec.motivo_revision,
            completeness=rec.completeness,
        )

    doc_type = DocumentType.DESCONOCIDO
    if rec.doc_type:
        try:
            doc_type = DocumentType(rec.doc_type)
        except ValueError:
            pass

    fecha = None
    if rec.fecha:
        try:
            from datetime import date as _date
            fecha = _date.fromisoformat(rec.fecha)
        except ValueError:
            fecha = None

    return DTEResponseSchema(
        archivo=rec.archivo_origen,
        doc_type=doc_type,
        ocr_engine=rec.ocr_engine or rec.ruta_extraccion or "unknown",
        ocr_avg_score=rec.ocr_avg_score or 0.0,
        folio=rec.nro_documento,
        fecha_emision=fecha,
        rut_emisor=rec.rut,
        razon_social=rec.proveedor,
        rut_receptor=None,
        total=rec.total,
        estado=rec.estado,
        motivo_revision=rec.motivo_revision,
        completeness=rec.completeness if rec.completeness is not None else (1.0 if rec.estado == "OK" else 0.5),
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Sube 1 archivo y procesa sincrónicamente",
)
async def upload_single(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archivo sin nombre")

    settings = load_settings()
    suffix = Path(file.filename).suffix or ".bin"
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target = UPLOAD_DIR / safe_name
    with target.open("wb") as f:
        f.write(await file.read())

    job_id = uuid.uuid4().hex[:12]
    try:
        await create_job(job_id, total_files=1, metadata={"original_name": file.filename})
        rec = process_one(target, settings)
        dte = _record_to_schema(rec)
        
        rut_to_save = rec.rut
        fecha_to_save = rec.fecha if isinstance(rec, InvoiceRecord) else rec.fecha_nacimiento
        total_to_save = getattr(rec, "total", None)
        proveedor_to_save = getattr(rec, "proveedor", None)
        folio_to_save = rec.numero_documento if isinstance(rec, CedulaRecord) else getattr(rec, "nro_documento", None)

        await add_job_record(
            job_id, rec.archivo_origen,
            estado=rec.estado, rut=rut_to_save, fecha=fecha_to_save,
            total=total_to_save, proveedor=proveedor_to_save, folio=folio_to_save,
            doc_type=str(dte.doc_type.value) if hasattr(dte, 'doc_type') else "cedula", ocr_engine=rec.ruta_extraccion,
            ocr_avg_score=0.0, missing_fields=[],
        )
        await update_job(job_id, status="done", processed=1, failed=0 if rec.estado != "REJECTED" else 1)
    finally:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass

    return UploadResponse(job_id=job_id, archivo=file.filename, result=dte)


@router.post(
    "/upload-batch",
    response_model=BatchUploadResponse,
    summary="Sube múltiples archivos y procesa sincrónicamente",
)
async def upload_batch(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Sin archivos")

    settings = load_settings()
    job_id = uuid.uuid4().hex[:12]
    await create_job(job_id, total_files=len(files))

    records: list[DTEResponseSchema | CedulaResponseSchema] = []
    raw_records = []
    processed = 0
    failed = 0

    for f in files:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix or ".bin"
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        target = UPLOAD_DIR / safe_name
        try:
            with target.open("wb") as fdisk:
                fdisk.write(await f.read())
            rec = process_one(target, settings)
            raw_records.append(rec)
            dte = _record_to_schema(rec)
            records.append(dte)
            
            rut_to_save = rec.rut
            fecha_to_save = rec.fecha if isinstance(rec, InvoiceRecord) else rec.fecha_nacimiento
            total_to_save = getattr(rec, "total", None)
            proveedor_to_save = getattr(rec, "proveedor", None)
            folio_to_save = rec.numero_documento if isinstance(rec, CedulaRecord) else getattr(rec, "nro_documento", None)

            await add_job_record(
                job_id, rec.archivo_origen,
                estado=rec.estado, rut=rut_to_save, fecha=fecha_to_save,
                total=total_to_save, proveedor=proveedor_to_save, folio=folio_to_save,
                doc_type=str(dte.doc_type.value) if hasattr(dte, 'doc_type') else "cedula", ocr_engine=rec.ruta_extraccion,
                ocr_avg_score=0.0, missing_fields=[], raw_text=getattr(rec, "raw_text", None),
            )
            if rec.estado == "REJECTED":
                failed += 1
            else:
                processed += 1
        except Exception as exc:
            failed += 1
            logger.exception(f"Error procesando {f.filename}")
        finally:
            try:
                target.unlink(missing_ok=True)
            except Exception:
                pass

    output_path = None
    if raw_records:
        from ocr_tributario.exporters.excel_writer import export_records
        output_dir = Path(settings.paths.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"Rendicion_Job_{job_id}.xlsx"
        try:
            export_records(raw_records, output_path=out, settings=settings)
            output_path = str(out)
        except Exception as exc:
            logger.exception(f"Error generando Excel para sync job {job_id}: {exc}")

    await update_job(job_id, status="done", processed=processed, failed=failed, output_path=output_path)
    return BatchUploadResponse(
        job_id=job_id,
        total=len(files),
        processed=processed,
        failed=failed,
        records=records,
    )


@router.post(
    "/queue",
    response_model=JobEnqueueResponse,
    summary="Encola archivos para procesamiento asíncrono (vía arq/Redis)",
)
async def enqueue(files: list[UploadFile] = File(...)):
    """Sube archivos y los encola. El worker procesa en background."""
    if not files:
        raise HTTPException(status_code=400, detail="Sin archivos")

    import redis.asyncio as _redis
    from arq.connections import create_pool, RedisSettings
    import urllib.parse
    
    url = load_settings().api.redis_url
    
    try:
        client = _redis.from_url(url)
        pong = await client.ping()
        await client.aclose()
        if not pong:
            raise Exception()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Redis no disponible. Inicia redis-server o usa /upload-batch sincrónico.",
        )

    job_id = uuid.uuid4().hex[:12]
    saved_paths: list[str] = []
    upload_subdir = UPLOAD_DIR / job_id
    upload_subdir.mkdir(parents=True, exist_ok=True)

    for f in files:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix or ".bin"
        safe_name = f"{uuid.uuid4().hex[:8]}{suffix}"
        target = upload_subdir / safe_name
        with target.open("wb") as fdisk:
            fdisk.write(await f.read())
        saved_paths.append(str(target.resolve()))

    if not saved_paths:
        raise HTTPException(status_code=400, detail="No se guardó ningún archivo")

    settings = load_settings()
    output_dir = Path(settings.paths.output_dir)
    output_path = output_dir / f"Rendicion_Job_{job_id}.xlsx"

    await create_job(
        job_id,
        total_files=len(saved_paths),
        metadata={
            "files": saved_paths,
            "output_path": str(output_path),
        },
    )

    parsed = urllib.parse.urlparse(url)
    redis_settings = RedisSettings(host=parsed.hostname or "localhost", port=parsed.port or 6379)
    arq_client = await create_pool(redis_settings)
    try:
        await arq_client.enqueue_job(
            "process_job",
            _queue_name="ocr-jobs",
            files=saved_paths,
            job_id=job_id,
            output_path=str(output_path),
        )
    finally:
        await arq_client.aclose()

    return JobEnqueueResponse(
        job_id=job_id,
        status="queued",
        total_files=len(saved_paths),
    )
