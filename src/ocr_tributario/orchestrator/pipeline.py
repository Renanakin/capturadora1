"""Orquestador end-to-end con EasyOCR como motor principal.

Arquitectura:
  1. Cargar imagen y preprocesar (OpenCV)
  2. OCR principal con EasyOCR (motor neuronal)
  3. Si EasyOCR da score bajo, fallback a Tesseract multi-PSM
  4. Clasificar tipo de documento (factura/boleta/NC/genérico)
  5. Parsear campos DTE según tipo
  6. (Opcional) Refinar con extracción por anclas (image_to_data)
  7. Persistir en InvoiceRecord + Excel
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from ocr_tributario.config.schema import Settings
from ocr_tributario.extractors.anchors import extract_by_anchors
from ocr_tributario.extractors.image_fallback import extract_pdf_image_fallback
from ocr_tributario.extractors.pdf_native import extract_native_pdf_data
from ocr_tributario.ingestion.router import route
from ocr_tributario.ingestion.scanner import scan_directory
from ocr_tributario.models.invoice import InvoiceRecord
from ocr_tributario.orchestrator.hitl import write_quarantine_excel
from ocr_tributario.preprocessing.opencv_pipeline import load_image, preprocess_image
from ocr_tributario.services.classify import DocumentType, classify_document
from ocr_tributario.services.ocr_easy import OCRResult, OCREasy
from ocr_tributario.services.ocr_tesseract import OCRTesseract
from ocr_tributario.services.parse_dte import DTEFields, parse_dte_fields
from ocr_tributario.validators.normalizers import normalize_mes
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
    by_type: dict[str, int] = None  # type: ignore

    def __post_init__(self):
        if self.by_type is None:
            self.by_type = {}


# Umbral mínimo de score promedio para considerar EasyOCR confiable
EASY_SCORE_THRESHOLD = 0.4


def _run_easy_or_tesseract(
    img_pre: "np.ndarray",
    settings: Settings,
) -> tuple[OCRResult, str]:
    """EasyOCR primero; si score muy bajo, Tesseract multi-PSM fallback."""
    warnings.filterwarnings("ignore")
    easy = OCREasy(langs=("es",), gpu=False)
    easy_result = easy.read_with_confidence_threshold(img_pre, min_score=0.3)
    logger.debug(f"EasyOCR: {easy_result}")

    if easy_result.avg_score >= EASY_SCORE_THRESHOLD and len(easy_result.lines) >= 3:
        return easy_result, "easy"

    # Fallback a Tesseract multi-PSM
    logger.debug(f"EasyOCR score bajo ({easy_result.avg_score:.3f}); fallback a Tesseract")
    tess = OCRTesseract(
        tesseract_cmd=settings.paths.tesseract_cmd,
        tessdata_prefix=settings.paths.tessdata_prefix,
    )
    tess_result = tess.read_multi_psm(img_pre, settings.ocr)
    return tess_result, "tesseract"


def _merge_dual_ocr(
    easy_result: OCRResult,
    tess_result: OCRResult,
    settings: Settings,
) -> OCRResult:
    """Combina resultados de EasyOCR + Tesseract quedándose con el mejor texto
    por métrica (RUT encontrado, fecha, total)."""
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

    easy_text = easy_result.full_text
    tess_text = tess_result.full_text

    # Si Tesseract tiene mejor score en campos críticos, usar sus líneas
    s_easy = _score(easy_text)
    s_tess = _score(tess_text)

    if s_tess > s_easy:
        logger.debug(f"Doble OCR: Tesseract mejor ({s_tess} vs {s_easy} Easy)")
        return OCRResult(
            lines=easy_result.lines + tess_result.lines,  # combinamos líneas
            full_text=tess_text + "\n" + easy_text,  # texto fallback primero
            avg_score=(easy_result.avg_score + tess_result.avg_score) / 2,
            engine="dual_tess_priority",
        )
    else:
        logger.debug(f"Doble OCR: EasyOCR mejor ({s_easy} vs {s_tess} Tess)")
        return OCRResult(
            lines=easy_result.lines + tess_result.lines,
            full_text=easy_text + "\n" + tess_text,
            avg_score=(easy_result.avg_score + tess_result.avg_score) / 2,
            engine="dual_easy_priority",
        )


def _run_dual_ocr(
    img_pre: "np.ndarray",
    settings: Settings,
) -> tuple[OCRResult, str]:
    """Ejecuta AMBOS motores (Easy + Tesseract) y combina resultados.

    Mejor recall: si EasyOCR falla en RUT pero Tesseract lo encuentra, se usa.
    """
    warnings.filterwarnings("ignore")
    easy = OCREasy(langs=("es",), gpu=False)
    easy_result = easy.read_with_confidence_threshold(img_pre, min_score=0.3)

    tess = OCRTesseract(
        tesseract_cmd=settings.paths.tesseract_cmd,
        tessdata_prefix=settings.paths.tessdata_prefix,
    )
    tess_result = tess.read_multi_psm(img_pre, settings.ocr)

    merged = _merge_dual_ocr(easy_result, tess_result, settings)
    return merged, "dual"


def _dte_to_invoice_record(
    source_path: Path,
    dte: DTEFields,
    ruta_extraccion: str,
) -> InvoiceRecord:
    """Convierte DTEFields a InvoiceRecord."""
    fecha_iso = dte.fecha_emision.isoformat() if dte.fecha_emision else None
    record = InvoiceRecord(
        archivo_origen=source_path.name,
        mes=normalize_mes(fecha_iso),
        fecha=fecha_iso,
        nro_documento=dte.folio,
        proveedor=dte.razon_social,
        rut=dte.rut_emisor,
        total=dte.total,
        ruta_extraccion=ruta_extraccion,
    )

    # Sin datos extraídos -> REJECTED (no llegó a nada)
    if not dte.has_any_data():
        record.estado = "REJECTED"
        record.motivo_revision = "OCR no extrajo ningún campo crítico (imagen ilegible o sin texto)"
        return record

    missing = dte.missing_required()
    if not missing:
        record.estado = "OK"
    else:
        record.estado = "QUARANTINE"
        record.motivo_revision = f"Faltan: {', '.join(missing)} | Completitud: {dte.completeness():.0%}"

    return record


def _record_from_pdf_native(source_path: Path, raw_text: str, ruta: str) -> InvoiceRecord:
    """Procesa PDF nativo (texto extraíble)."""
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
) -> InvoiceRecord:
    """Procesa un único documento. Excepciones se reflejan como REJECTED."""
    from ocr_tributario.ingestion.scanner import DocumentInput
    from ocr_tributario.utils.magic_bytes import detect_file_type

    ftype = detect_file_type(source_path)
    doc = DocumentInput(path=source_path, file_type=ftype)
    ruta = route(doc)

    try:
        # PDF nativo: texto directo
        if ruta == "pdf_native":
            data = extract_native_pdf_data(source_path)
            return _record_from_pdf_native(source_path, data.get("raw_text", ""), "pdf_native")

        # PDF escaneado: render + OCR
        if ruta == "pdf_image":
            data = extract_pdf_image_fallback(
                source_path,
                hsv_cfg=settings.hsv_red,
                ocr_cfg=settings.ocr,
                tesseract_cmd=settings.paths.tesseract_cmd,
                tessdata_prefix=settings.paths.tessdata_prefix,
            )
            # Crear OCRResult fake a partir del texto para reusar pipeline
            from ocr_tributario.services.ocr_easy import OCRLine, OCRResult
            fake_result = OCRResult(
                lines=[OCRLine(text=t, score=0.5, box=[(0, 0)]) for t in data.get("raw_text", "").splitlines() if t.strip()],
                full_text=data.get("raw_text", ""),
                avg_score=0.5,
                engine="pdf_image_fallback",
            )
            doc_type = classify_document(fake_result)
            dte = parse_dte_fields(doc_type, fake_result)
            return _dte_to_invoice_record(source_path, dte, "pdf_image")

        # Imagen: doble OCR (Easy + Tesseract) → clasificar → parsear
        if ruta == "image":
            img = load_image(source_path)
            pre = preprocess_image(img)

            # Doble OCR: EasyOCR + Tesseract combinados (mayor recall)
            ocr_result, engine_used = _run_dual_ocr(pre, settings)

            # Clasificar tipo de documento
            doc_type = classify_document(ocr_result)
            logger.debug(f"{source_path.name} → {doc_type.value} (engine={engine_used}, score={ocr_result.avg_score:.3f})")

            # Extraer anclas (para campos faltantes)
            anchor = None
            try:
                anchor = extract_by_anchors(pre, settings.ocr)
            except Exception as exc:
                logger.debug(f"anchor extraction failed: {exc}")

            # Parsear campos DTE según tipo
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
    """Procesa todos los documentos de un directorio."""
    docs = scan_directory(input_dir)
    if not docs:
        logger.warning(f"Sin documentos en {input_dir}")
        return ProcessingReport(records=[])

    records: list[InvoiceRecord] = []
    by_type: dict[str, int] = {}

    for doc in tqdm(docs, desc="Procesando", unit="doc"):
        rec = process_one(doc.path, settings)
        records.append(rec)

    # Agregar estadísticas por tipo
    from ocr_tributario.services.classify import classify_document
    from ocr_tributario.preprocessing.opencv_pipeline import load_image, preprocess_image
    from ocr_tributario.services.ocr_easy import OCREasy

    # Recalcular estadísticas por tipo requiere re-OCR; usar la info ya guardada
    for rec in records:
        # Heurística simple: ver si el archivo es boleta/factura por nombre
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