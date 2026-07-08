"""Orquestador end-to-end (Fase 8, simplificado para Nivel B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from ocr_tributario.config.schema import Settings
from ocr_tributario.extractors.anchors import extract_by_anchors
from ocr_tributario.extractors.image_fallback import extract_pdf_image_fallback
from ocr_tributario.extractors.ocr_tesseract import configure_tesseract, ocr_image
from ocr_tributario.extractors.pdf_native import extract_native_pdf_data
from ocr_tributario.ingestion.router import route
from ocr_tributario.ingestion.scanner import scan_directory
from ocr_tributario.models.invoice import InvoiceRecord
from ocr_tributario.orchestrator.hitl import write_quarantine_excel
from ocr_tributario.preprocessing.opencv_pipeline import load_image, preprocess_image
from ocr_tributario.validators.normalizers import (
    extract_provider,
    normalize_mes,
    normalize_provider_name,
)
from ocr_tributario.validators.regex_patterns import (
    extract_date,
    extract_folio,
    extract_rut,
    extract_total,
)
from ocr_tributario.validators.rut import validate_rut


@dataclass
class ProcessingReport:
    records: list[InvoiceRecord]
    ok: int = 0
    quarantine: int = 0
    failed: int = 0


def _build_record_from_text(
    source_path: Path,
    raw_text: str,
    ruta_extraccion: str,
) -> InvoiceRecord:
    fecha = extract_date(raw_text)
    rut = extract_rut(raw_text)
    total = extract_total(raw_text)
    folio = extract_folio(raw_text)
    proveedor = extract_provider(raw_text, rut_canonico=rut)

    record = InvoiceRecord(
        archivo_origen=source_path.name,
        mes=normalize_mes(fecha.isoformat() if fecha else None),
        fecha=fecha.isoformat() if fecha else None,
        nro_documento=folio,
        rut=rut,
        total=total,
        proveedor=proveedor,
        ruta_extraccion=ruta_extraccion,
    )

    if record.is_valid_for_excel():
        record.estado = "OK"
    else:
        record.estado = "QUARANTINE"
        missing = [k for k in ("fecha", "rut", "total") if not getattr(record, k)]
        record.motivo_revision = "Faltan campos: " + ", ".join(missing)

    return record


def _merge_anchor_into_record(
    record: InvoiceRecord,
    anchor_result,
) -> InvoiceRecord:
    """Si regex no extrajo un campo y anclas sí, lo usa. También aplica Módulo 11."""
    # RUT: si regex no dio, intenta con anclas
    if not record.rut and anchor_result.rut:
        canonico = validate_rut(anchor_result.rut)
        if canonico:
            record.rut = canonico

    # Total
    if record.total is None and anchor_result.total is not None:
        record.total = anchor_result.total

    # Neto (si no hay total, usa neto como fallback)
    if record.total is None and anchor_result.neto is not None:
        record.total = anchor_result.neto

    # Fecha
    if not record.fecha and anchor_result.fecha:
        record.fecha = anchor_result.fecha.isoformat() if hasattr(anchor_result.fecha, "isoformat") else anchor_result.fecha
        record.mes = normalize_mes(record.fecha)

    # Folio
    if not record.nro_documento and anchor_result.folio:
        record.nro_documento = anchor_result.folio

    # Proveedor
    if not record.proveedor and anchor_result.proveedor:
        record.proveedor = normalize_provider_name(anchor_result.proveedor)

    # Re-evaluar estado
    if record.is_valid_for_excel():
        record.estado = "OK"
        record.motivo_revision = None
    elif record.estado == "QUARANTINE":
        missing = [k for k in ("fecha", "rut", "total") if not getattr(record, k)]
        record.motivo_revision = "Faltan campos: " + ", ".join(missing)

    return record


def process_one(
    source_path: Path,
    settings: Settings,
) -> InvoiceRecord:
    """Procesa un único documento. Cualquier excepción se refleja como REJECTED."""
    from ocr_tributario.ingestion.scanner import DocumentInput
    from ocr_tributario.utils.magic_bytes import detect_file_type

    ftype = detect_file_type(source_path)
    doc = DocumentInput(path=source_path, file_type=ftype)
    ruta = route(doc)

    try:
        if ruta == "pdf_native":
            data = extract_native_pdf_data(source_path)
            return _build_record_from_text(source_path, data.get("raw_text", ""), "pdf_native")

        if ruta == "pdf_image":
            data = extract_pdf_image_fallback(
                source_path,
                hsv_cfg=settings.hsv_red,
                ocr_cfg=settings.ocr,
                tesseract_cmd=settings.paths.tesseract_cmd,
                tessdata_prefix=settings.paths.tessdata_prefix,
            )
            record = _build_record_from_text(source_path, data.get("raw_text", ""), "pdf_image")
            if not record.is_valid_for_excel():
                # intentar anclas
                anchor = data.get("anchor_result")
                if anchor:
                    _merge_anchor_into_record(record, anchor)
            return record

        if ruta == "image":
            configure_tesseract(settings.paths.tesseract_cmd, settings.paths.tessdata_prefix)
            img = load_image(source_path)
            pre = preprocess_image(img)
            from ocr_tributario.extractors.ocr_tesseract import ocr_array_multi_psm
            text, ocr_meta = ocr_array_multi_psm(pre, settings.ocr)
            record = _build_record_from_text(source_path, text, "image")
            # Si faltan campos, intentar con extracción por anclas (más robusta)
            if not record.is_valid_for_excel():
                anchor = extract_by_anchors(pre, settings.ocr)
                _merge_anchor_into_record(record, anchor)
            return record

        record = InvoiceRecord(
            archivo_origen=source_path.name,
            estado="REJECTED",
            motivo_revision=f"Ruta desconocida: {ruta}",
        )
        return record

    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Fallo procesando {source_path.name}")
        return InvoiceRecord(
            archivo_origen=source_path.name,
            estado="REJECTED",
            motivo_revision=f"Excepción: {type(exc).__name__}: {exc}",
        )


def process_directory(input_dir: Path, settings: Settings) -> ProcessingReport:
    """Procesa todos los documentos de un directorio."""
    docs = scan_directory(input_dir)
    if not docs:
        logger.warning(f"Sin documentos en {input_dir}")
        return ProcessingReport(records=[])

    records: list[InvoiceRecord] = []
    for doc in tqdm(docs, desc="Procesando", unit="doc"):
        rec = process_one(doc.path, settings)
        records.append(rec)

    ok = sum(1 for r in records if r.estado == "OK")
    quarantine = [r for r in records if r.estado == "QUARANTINE"]
    failed = sum(1 for r in records if r.estado == "REJECTED")

    if quarantine:
        write_quarantine_excel(quarantine, settings)

    logger.info(f"Resumen: OK={ok} · QUARANTINE={len(quarantine)} · REJECTED={failed}")
    return ProcessingReport(records=records, ok=ok, quarantine=len(quarantine), failed=failed)