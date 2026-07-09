"""Orquestador end-to-end con PaddleOCR como motor principal.

Arquitectura:
  1. Cargar imagen y preprocesar (OpenCV)
  2. OCR principal con PaddleOCR (motor neuronal, fallback Tesseract)
  3. Clasificar tipo de documento (factura/boleta/NC/cedula/genérico)
  4. Parsear campos según tipo (DTE o Cedula)
  5. Segmentación HSV automática para DTEs (recuadro rojo), con fallback
  6. (Opcional) Refinar con extracción por anclas
  7. Persistir
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from tqdm import tqdm
import cv2

from ocr_tributario.config.schema import Settings
from ocr_tributario.extractors.anchors import extract_by_anchors
from ocr_tributario.extractors.image_fallback import extract_pdf_image_fallback
from ocr_tributario.extractors.pdf_native import extract_native_pdf_data
from ocr_tributario.ingestion.router import route
from ocr_tributario.ingestion.scanner import scan_directory
from ocr_tributario.models.invoice import InvoiceRecord
from ocr_tributario.models.cedula import CedulaRecord
from ocr_tributario.orchestrator.hitl import write_quarantine_excel
from ocr_tributario.preprocessing.opencv_pipeline import load_image, preprocess_image, adaptive_threshold
from ocr_tributario.preprocessing.hsv_segmenter import extract_sii_red_box
from ocr_tributario.services.classify import DocumentType, classify_document
from ocr_tributario.services.ocr_paddle import OCRResult, OCRPaddle
from ocr_tributario.services.ocr_tesseract import OCRTesseract
from ocr_tributario.services.parse_dte import DTEFields, parse_dte_fields
from ocr_tributario.services.parse_cedula import parse_cedula_fields
from ocr_tributario.validators.normalizers import normalize_mes
from ocr_tributario.validators.regex_patterns import (
    extract_date,
    extract_folio,
    extract_rut,
    extract_total,
)


@dataclass
class ProcessingReport:
    records: list[InvoiceRecord | CedulaRecord]
    ok: int = 0
    quarantine: int = 0
    failed: int = 0
    by_type: dict[str, int] = None  # type: ignore

    def __post_init__(self):
        if self.by_type is None:
            self.by_type = {}


def _merge_dual_ocr(
    paddle_result: OCRResult,
    tess_result: OCRResult,
    settings: Settings,
) -> OCRResult:
    """Combina resultados de PaddleOCR + Tesseract quedándose con el mejor texto."""
    from ocr_tributario.validators.regex_patterns import (
        _RUT_INLINE,
        extract_date,
        extract_total,
    )

    def _score(text: str) -> int:
        s = 0
        if _RUT_INLINE.search(text):
            s += 5
        if extract_date(text):
            s += 3
        if extract_total(text):
            s += 4
        if len(text.strip()) > 50:
            s += 1
        return s

    paddle_text = paddle_result.full_text
    tess_text = tess_result.full_text

    s_paddle = _score(paddle_text)
    s_tess = _score(tess_text)

    if s_tess > s_paddle:
        logger.debug(f"Doble OCR: Tesseract mejor ({s_tess} vs {s_paddle} Paddle)")
        return OCRResult(
            lines=paddle_result.lines + tess_result.lines,
            full_text=tess_text + "\n" + paddle_text,
            avg_score=(paddle_result.avg_score + tess_result.avg_score) / 2,
            engine="dual_tess_priority",
        )
    else:
        logger.debug(f"Doble OCR: PaddleOCR mejor ({s_paddle} vs {s_tess} Tess)")
        return OCRResult(
            lines=paddle_result.lines + tess_result.lines,
            full_text=paddle_text + "\n" + tess_text,
            avg_score=(paddle_result.avg_score + tess_result.avg_score) / 2,
            engine="dual_paddle_priority",
        )


def _run_dual_ocr(
    img_pre: "np.ndarray",
    settings: Settings,
) -> tuple[OCRResult, str]:
    """Ejecuta AMBOS motores (Paddle + Tesseract) y combina resultados."""
    warnings.filterwarnings("ignore")
    paddle = OCRPaddle(lang='es')
    paddle_result = paddle.read_with_confidence_threshold(img_pre, min_score=0.3)

    tess = OCRTesseract(
        tesseract_cmd=settings.paths.tesseract_cmd,
        tessdata_prefix=settings.paths.tessdata_prefix,
    )
    tess_result = tess.read_multi_psm(img_pre, settings.ocr)

    merged = _merge_dual_ocr(paddle_result, tess_result, settings)
    return merged, "dual"


def _dte_to_invoice_record(
    source_path: Path,
    dte: DTEFields,
    ruta_extraccion: str,
) -> InvoiceRecord:
    from ocr_tributario.services.parse_dte import to_invoice_record
    return to_invoice_record(dte, source_path, ruta_extraccion)


def _record_from_pdf_native(source_path: Path, raw_text: str, ruta: str) -> InvoiceRecord:
    fecha = extract_date(raw_text)
    rut = extract_rut(raw_text)
    total = extract_total(raw_text)
    folio = extract_folio(raw_text)
    from ocr_tributario.validators.normalizers import extract_provider
    proveedor = extract_provider(raw_text, rut_canonico=rut)

    record = InvoiceRecord(
        archivo_origen=source_path.name,
        mes=normalize_mes(fecha.isoformat() if fecha else None),
        fecha=fecha.isoformat() if fecha else None,
        nro_documento=folio,
        rut=rut,
        total=total,
        proveedor=proveedor,
        ruta_extraccion=ruta,
    )
    if record.is_valid_for_excel():
        record.estado = "OK"
    else:
        missing = [k for k in ("fecha", "rut", "total") if not getattr(record, k)]
        record.estado = "QUARANTINE"
        record.motivo_revision = f"Faltan: {', '.join(missing)}"
    return record


def process_one(
    source_path: Path,
    settings: Settings,
) -> InvoiceRecord | CedulaRecord:
    from ocr_tributario.ingestion.scanner import DocumentInput
    from ocr_tributario.utils.magic_bytes import detect_file_type

    ftype = detect_file_type(source_path)
    doc = DocumentInput(path=source_path, file_type=ftype)
    ruta = route(doc)

    try:
        if ruta == "pdf_native":
            data = extract_native_pdf_data(source_path)
            return _record_from_pdf_native(source_path, data.get("raw_text", ""), "pdf_native")

        if ruta == "pdf_image":
            data = extract_pdf_image_fallback(
                source_path,
                hsv_cfg=settings.hsv_red,
                ocr_cfg=settings.ocr,
                tesseract_cmd=settings.paths.tesseract_cmd,
                tessdata_prefix=settings.paths.tessdata_prefix,
            )
            from ocr_tributario.services.ocr_paddle import OCRLine, OCRResult
            fake_result = OCRResult(
                lines=[OCRLine(text=t, score=0.5, box=[(0, 0)]) for t in data.get("raw_text", "").splitlines() if t.strip()],
                full_text=data.get("raw_text", ""),
                avg_score=0.5,
                engine="pdf_image_fallback",
            )
            doc_type = classify_document(fake_result)
            if doc_type == DocumentType.CEDULA:
                return parse_cedula_fields(fake_result, source_path.name, "pdf_image_fallback")
            dte = parse_dte_fields(doc_type, fake_result)
            return _dte_to_invoice_record(source_path, dte, "pdf_image")

        if ruta == "image":
            img = load_image(source_path)
            
            # 1. Intentar segmentación HSV para recuadro rojo (eficaz para DTE)
            hsv_crop_info = extract_sii_red_box(img, settings.hsv_red)
            hsv_text = ""
            if hsv_crop_info:
                crop, _ = hsv_crop_info
                # OCR rápido al recuadro rojo con Tesseract
                tess = OCRTesseract(
                    tesseract_cmd=settings.paths.tesseract_cmd,
                    tessdata_prefix=settings.paths.tessdata_prefix,
                )
                res_box = tess.read_multi_psm(crop, settings.ocr)
                hsv_text = res_box.full_text

            # 2. Preprocesamiento general y OCR completo
            pre = preprocess_image(img)
            
            # Fallback para térmicas (si no hubo recuadro rojo detectado) -> Aplicar umbralizado fuerte
            if not hsv_crop_info:
                pre = adaptive_threshold(pre)

            ocr_result, engine_used = _run_dual_ocr(pre, settings)
            
            # Inyectar texto del recuadro rojo si se encontró
            if hsv_text:
                ocr_result.full_text = hsv_text + "\n" + ocr_result.full_text

            doc_type = classify_document(ocr_result)
            logger.debug(f"{source_path.name} → {doc_type.value} (engine={engine_used}, score={ocr_result.avg_score:.3f})")

            # 3. Parseo según tipo
            if doc_type == DocumentType.CEDULA:
                return parse_cedula_fields(ocr_result, source_path.name, f"image_{engine_used}")

            anchor = None
            try:
                anchor = extract_by_anchors(pre, settings.ocr)
            except Exception as exc:
                logger.debug(f"anchor extraction failed: {exc}")

            dte = parse_dte_fields(doc_type, ocr_result, anchor_result=anchor)
            return _dte_to_invoice_record(source_path, dte, f"image_{engine_used}")

        return InvoiceRecord(
            archivo_origen=source_path.name,
            estado="REJECTED",
            motivo_revision=f"Ruta desconocida: {ruta}",
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Fallo procesando {source_path.name}")
        return InvoiceRecord(
            archivo_origen=source_path.name,
            estado="REJECTED",
            motivo_revision=f"Excepción: {type(exc).__name__}: {exc}",
        )


def process_directory(input_dir: Path, settings: Settings) -> ProcessingReport:
    docs = scan_directory(input_dir)
    if not docs:
        logger.warning(f"Sin documentos en {input_dir}")
        return ProcessingReport(records=[])

    records: list[InvoiceRecord | CedulaRecord] = []
    by_type: dict[str, int] = {}

    for doc in tqdm(docs, desc="Procesando", unit="doc"):
        rec = process_one(doc.path, settings)
        records.append(rec)

    for rec in records:
        if isinstance(rec, CedulaRecord):
            t = "cedula"
        else:
            name = rec.archivo_origen.lower()
            if "factura" in name:
                t = "factura"
            elif "boleta" in name:
                t = "boleta"
            else:
                t = "otro"
        by_type[t] = by_type.get(t, 0) + 1

    ok = sum(1 for r in records if r.estado == "OK")
    quarantine = [r for r in records if r.estado == "QUARANTINE"]
    failed = sum(1 for r in records if r.estado == "REJECTED")

    if quarantine:
        write_quarantine_excel(quarantine, settings)

    logger.info(f"Resumen: OK={ok} · QUARANTINE={len(quarantine)} · REJECTED={failed}")
    return ProcessingReport(records=records, ok=ok, quarantine=len(quarantine), failed=failed, by_type=by_type)