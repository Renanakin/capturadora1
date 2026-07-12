"""Parser DTE específico por tipo de documento.

Para cada tipo (factura, boleta, NC, guía) aplica heurísticas de extracción
apropiadas. Boletas no tienen RUT receptor; facturas sí; notas de crédito
tienen referencia a factura original; etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ocr_tributario.services.classify import DocumentType


@dataclass
class DTEFields:
    """Campos extraídos de un DTE, con scores por campo."""
    # Identificación
    doc_type: DocumentType
    folio: int | None = None
    folio_score: float = 0.0

    # Emisor
    rut_emisor: str | None = None
    rut_emisor_score: float = 0.0
    razon_social: str | None = None
    razon_social_score: float = 0.0
    giro: str | None = None

    # Receptor (solo facturas y NC)
    rut_receptor: str | None = None
    rut_receptor_score: float = 0.0

    # Montos
    neto: int | None = None
    neto_score: float = 0.0
    iva: int | None = None
    iva_score: float = 0.0
    total: int | None = None
    total_score: float = 0.0
    exento: int | None = None

    # Fechas
    fecha_emision: date | None = None
    fecha_emision_score: float = 0.0

    # Referencia (solo NC)
    folio_referencia: int | None = None
    fecha_referencia: date | None = None

    # Items (resumen)
    items: list[dict] = field(default_factory=list)

    # Metadatos
    raw_text: str = ""
    ocr_engine: str = ""
    ocr_avg_score: float = 0.0

    def completeness(self) -> float:
        """Porcentaje de campos críticos extraídos (0-1)."""
        required = self.required_fields()
        if not required:
            return 0.0
        found = sum(1 for f in required if getattr(self, f) is not None)
        return found / len(required)

    def required_fields(self) -> list[str]:
        """Campos requeridos según el tipo de documento."""
        return {
            DocumentType.FACTURA_ELECTRONICA: ["folio", "rut_emisor", "razon_social", "fecha_emision", "neto", "iva", "total"],
            DocumentType.BOLETA_ELECTRONICA: ["folio", "rut_emisor", "razon_social", "fecha_emision", "total"],
            DocumentType.NOTA_CREDITO: ["folio", "rut_emisor", "razon_social", "fecha_emision", "total"],
            DocumentType.GUIA_DESPACHO: ["folio", "rut_emisor", "razon_social", "fecha_emision"],
            DocumentType.DTE_GENERICO: ["rut_emisor", "fecha_emision", "total"],
            DocumentType.INVOICE_EXTRANJERA: ["fecha_emision", "total"],
            # DESCONOCIDO: requiere al menos 1 campo crítico para no quedar como "OK vacío"
            DocumentType.DESCONOCIDO: ["rut_emisor", "fecha_emision", "total"],
        }.get(self.doc_type, [])

    def missing_required(self) -> list[str]:
        """Lista de campos requeridos que faltan."""
        return [f for f in self.required_fields() if getattr(self, f) is None]

    def has_any_data(self) -> bool:
        """True si extrajimos al menos un campo crítico."""
        return any([
            self.rut_emisor, self.razon_social, self.fecha_emision,
            self.total, self.folio,
        ])


def parse_dte_fields(
    doc_type: DocumentType,
    ocr_result,
    anchor_result=None,
) -> DTEFields:
    """Parsea campos DTE desde OCR + anclas según el tipo de documento.

    Usa los extractores existentes (regex + anclas) y los organiza en DTEFields.
    """
    from ocr_tributario.validators.regex_patterns import (
        extract_date,
        extract_folio,
        extract_rut,
        extract_total,
    )
    from ocr_tributario.validators.normalizers import (
        extract_provider,
        normalize_mes,
        normalize_provider_name,
    )

    text = ocr_result.full_text
    fields = DTEFields(
        doc_type=doc_type,
        raw_text=text,
        ocr_engine=ocr_result.engine,
        ocr_avg_score=ocr_result.avg_score,
    )

    # Emisor RUT (primera aparición de RUT)
    fields.rut_emisor = extract_rut(text)
    fields.rut_emisor_score = 0.8 if fields.rut_emisor else 0.0

    # Razón social
    fields.razon_social = extract_provider(text, rut_canonico=fields.rut_emisor)
    fields.razon_social_score = 0.7 if fields.razon_social else 0.0

    # Folio
    fields.folio = extract_folio(text)
    fields.folio_score = 0.8 if fields.folio else 0.0

    # Fecha emisión
    fecha = extract_date(text)
    fields.fecha_emision = fecha
    fields.fecha_emision_score = 0.85 if fecha else 0.0

    # Total
    fields.total = extract_total(text)
    fields.total_score = 0.8 if fields.total is not None else 0.0

    # Si tenemos anclas, intentar mejorar campos faltantes
    if anchor_result:
        if not fields.total and anchor_result.total is not None:
            fields.total = anchor_result.total
            fields.total_score = 0.7
        if not fields.folio and anchor_result.folio:
            fields.folio = anchor_result.folio
            fields.folio_score = 0.7
        if not fields.razon_social and anchor_result.proveedor:
            fields.razon_social = normalize_provider_name(anchor_result.proveedor)
            fields.razon_social_score = 0.7
        if not fields.fecha_emision and anchor_result.fecha:
            from datetime import datetime as _dt
            if isinstance(anchor_result.fecha, str):
                try:
                    fields.fecha_emision = _dt.fromisoformat(anchor_result.fecha).date()
                except ValueError:
                    pass
            else:
                fields.fecha_emision = anchor_result.fecha
            fields.fecha_emision_score = 0.7 if fields.fecha_emision else 0.0
        if not fields.rut_emisor and anchor_result.rut:
            from ocr_tributario.validators.rut import validate_rut
            canonico = validate_rut(anchor_result.rut)
            if canonico:
                fields.rut_emisor = canonico
                fields.rut_emisor_score = 0.7

    # Campos específicos por tipo
    if doc_type == DocumentType.INVOICE_EXTRANJERA:
        if not fields.rut_emisor:
            fields.rut_emisor = "EXTRANJERO"
            fields.rut_emisor_score = 1.0

    if doc_type == DocumentType.FACTURA_ELECTRONICA:
        # Factura tiene RUT receptor (segundo RUT distinto al emisor)
        all_ruts = _extract_all_ruts(text)
        if fields.rut_emisor and len(all_ruts) >= 2:
            others = [r for r in all_ruts if r != fields.rut_emisor]
            if others:
                fields.rut_receptor = others[0]
                fields.rut_receptor_score = 0.7

        # Neto e IVA (factura electrónica los muestra)
        if anchor_result:
            if anchor_result.neto:
                fields.neto = anchor_result.neto
                fields.neto_score = 0.7
            if anchor_result.iva:
                fields.iva = anchor_result.iva
                fields.iva_score = 0.7

        # Si no hay neto pero sí total y iva, derivar
        if fields.neto is None and fields.total is not None and fields.iva is not None:
            derived = fields.total - fields.iva
            if derived > 0:
                fields.neto = derived
                fields.neto_score = 0.5

    return fields


def to_invoice_record(dte: DTEFields, source_path: Path, ruta_extraccion: str) -> "InvoiceRecord":
    """Convierte DTEFields en InvoiceRecord para integracion con pipeline legacy."""
    from ocr_tributario.models.invoice import InvoiceRecord
    from ocr_tributario.validators.normalizers import normalize_mes

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
        doc_type=dte.doc_type.value if hasattr(dte.doc_type, "value") else str(dte.doc_type),
        ocr_engine=dte.ocr_engine,
        ocr_avg_score=dte.ocr_avg_score,
        completeness=dte.completeness(),
        raw_text=dte.raw_text,
    )
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


def _extract_all_ruts(text: str) -> list[str]:
    """Extrae TODOS los RUTs válidos del texto."""
    from ocr_tributario.validators.regex_patterns import extract_rut
    from ocr_tributario.validators.rut import validate_rut
    from ocr_tributario.utils.magic_bytes import detect_file_type  # noqa

    # Buscar múltiples RUTs
    from ocr_tributario.validators.regex_patterns import _RUT_INLINE
    import re

    # Primero buscar menciones explícitas "RUT:" o "R.U.T.:"
    pattern = re.compile(r"R\.?U\.?T\.?\s*[:N°ºo\.]*\s*(\d[\d\.\-Kk]{6,15})", re.IGNORECASE)
    seen: set[str] = set()
    out: list[str] = []
    for m in pattern.finditer(text):
        cand = m.group(1)
        canonico = validate_rut(cand)
        if canonico and canonico not in seen:
            seen.add(canonico)
            out.append(canonico)
    return out