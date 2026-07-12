from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from ocr_tributario.api.schemas import JobDetail, JobStatus
from ocr_tributario.db import get_job, list_job_records, list_jobs

router = APIRouter()

@router.get(
    "/{job_id}",
    response_model=JobDetail,
    summary="Detalle de un job (incluye registros extraídos)",
)
async def job_detail(job_id: str):
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} no existe")
    records = await list_job_records(job_id)
    return JobDetail(
        id=job.id,
        status=job.status,
        total_files=job.total_files,
        processed=job.processed,
        failed=job.failed,
        output_path=job.output_path,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        records=records,
    )

@router.get(
    "/{job_id}/download",
    summary="Descarga el Excel generado por el job",
)
async def job_download(job_id: str):
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} no existe")
    if not job.output_path:
        raise HTTPException(status_code=404, detail="Job aún no tiene Excel generado")
    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {job.output_path}")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )

@router.get(
    "",
    response_model=list[JobStatus],
    summary="Lista los últimos jobs",
)
async def jobs_list(limit: int = Query(50, ge=1, le=500)):
    jobs = await list_jobs(limit=limit)
    return [
        JobStatus(
            id=j.id, status=j.status, total_files=j.total_files,
            processed=j.processed, failed=j.failed, output_path=j.output_path,
            created_at=j.created_at, updated_at=j.updated_at, error=j.error,
        )
        for j in jobs
    ]

from pydantic import BaseModel

class CorrectionRequest(BaseModel):
    proveedor: str
    total: int | None = None
    fecha: str | None = None
    rut: str | None = None

@router.post(
    "/{job_id}/records/{archivo}/correct",
    summary="Aplica corrección manual a un registro y auto-aprende la plantilla",
)
async def correct_record(job_id: str, archivo: str, correction: CorrectionRequest):
    records = await list_job_records(job_id)
    record = next((r for r in records if r["archivo"] == archivo), None)
    if not record:
        raise HTTPException(status_code=404, detail="Registro no encontrado en el job")
        
    raw_text = record.get("raw_text")
    if raw_text and correction.proveedor:
        from ocr_tributario.services.template_engine import TemplateEngine
        engine = TemplateEngine()
        engine.learn_template(
            proveedor=correction.proveedor,
            ocr_text=raw_text,
            total_real=correction.total,
            fecha_real=correction.fecha,
            rut=correction.rut
        )
        
    # TODO: Actualizar el record en la base de datos para pasarlo a OK y re-generar el Excel.
    # Por simplicidad ahora solo procesa el aprendizaje.
    
    return {"status": "ok", "message": "Corrección aprendida y guardada como plantilla"}

