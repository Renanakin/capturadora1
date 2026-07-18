"""Script de evaluación pre-deploy.

Ejecuta el pipeline sobre `documentos_ingresados` y reporta:
- Total procesados
- OK / QUARANTINE / REJECTED
- % OK (métrica pre-deploy)
- Desglose de campos faltantes en QUARANTINE
- Por tipo de documento (pdf, image, .eml, etc.)
- Por tipo de ruta (pdf_native, pdf_image, image)
- Por doc_type (factura, boleta, cedula, etc.)

Uso:
    python -m scripts.eval_documentos
    python -m scripts.eval_documentos --input otra_carpeta --out reporte.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Asegurar import del paquete
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ocr_tributario.config.loader import load_settings  # noqa: E402
from ocr_tributario.ingestion.router import route  # noqa: E402
from ocr_tributario.ingestion.scanner import DocumentInput, scan_directory  # noqa: E402
from ocr_tributario.orchestrator.pipeline import process_one  # noqa: E402
from ocr_tributario.utils.magic_bytes import detect_file_type  # noqa: E402


def _campos_clave(rec) -> dict:
    """Devuelve qué campos críticos están presentes / faltan."""
    checks = {
        "fecha": bool(rec.fecha),
        "rut": bool(rec.rut),
        "total": rec.total is not None,
        "proveedor": bool(rec.proveedor),
        "nro_documento": rec.nro_documento is not None,
    }
    return checks


def _ruta_de(doc: DocumentInput) -> str:
    try:
        return route(doc) or "?"
    except Exception:
        return "?"


def evaluar(input_dir: Path, output_json: Path | None) -> dict:
    settings = load_settings()
    docs = scan_directory(input_dir)
    if not docs:
        return {"error": f"Sin documentos en {input_dir}"}

    records = []
    started = time.perf_counter()
    for d in docs:
        rec = process_one(d.path, settings)
        records.append((d, rec))
    elapsed = time.perf_counter() - started

    total = len(records)
    ok = sum(1 for _, r in records if r.estado == "OK")
    quar = sum(1 for _, r in records if r.estado == "QUARANTINE")
    rej = sum(1 for _, r in records if r.estado == "REJECTED")

    # Porcentaje OK es la métrica de "go a pre-deploy"
    pct_ok = (ok / total) * 100 if total else 0
    pct_usable = ((ok + quar) / total) * 100 if total else 0  # proceso completo, sin crashes

    # Faltantes en QUARANTINE
    faltantes = Counter()
    for _, r in records:
        if r.estado == "QUARANTINE":
            for k, present in _campos_clave(r).items():
                if not present:
                    faltantes[k] += 1

    # Por ruta de ingestión
    por_ruta = defaultdict(lambda: {"ok": 0, "quarantine": 0, "rejected": 0})
    for d, r in records:
        ruta = _ruta_de(d)
        por_ruta[ruta][r.estado.lower()] = por_ruta[ruta].get(r.estado.lower(), 0) + 1

    # Por doc_type
    por_doctype = defaultdict(lambda: {"ok": 0, "quarantine": 0, "rejected": 0, "total": 0})
    for _, r in records:
        dt = getattr(r, "doc_type", None) or "?"
        bucket = por_doctype[dt]
        bucket["total"] += 1
        bucket[r.estado.lower()] = bucket.get(r.estado.lower(), 0) + 1

    # Por extensión
    por_ext = Counter()
    for d, _ in records:
        por_ext[d.path.suffix.lower() or "(sin ext)"] += 1

    # Detalle por documento (para inspección)
    detalle = []
    for d, r in records:
        raw_text = getattr(r, "raw_text", None) or ""
        det = {
            "archivo": d.path.name,
            "ext": d.path.suffix.lower(),
            "ruta": _ruta_de(d),
            "estado": r.estado,
            "doc_type": getattr(r, "doc_type", None),
            "fecha": getattr(r, "fecha", None),
            "rut": getattr(r, "rut", None),
            "total": getattr(r, "total", None),
            "proveedor": getattr(r, "proveedor", None),
            "nro_documento": getattr(r, "nro_documento", None),
            "motivo": getattr(r, "motivo_revision", None),
            "ruta_extraccion": getattr(r, "ruta_extraccion", None),
            "raw_text_preview": raw_text[:1500] if raw_text else "",
        }
        detalle.append(det)

    reporte = {
        "input_dir": str(input_dir),
        "total": total,
        "ok": ok,
        "quarantine": quar,
        "rejected": rej,
        "pct_ok": round(pct_ok, 2),
        "pct_usable": round(pct_usable, 2),
        "elapsed_sec": round(elapsed, 2),
        "faltantes_quarantine": dict(faltantes),
        "por_ruta": {k: dict(v) for k, v in por_ruta.items()},
        "por_doc_type": {k: dict(v) for k, v in por_doctype.items()},
        "por_extension": dict(por_ext),
        "detalle": detalle,
    }

    if output_json:
        output_json.write_bytes(
            json.dumps(reporte, indent=2, ensure_ascii=False).encode("utf-8")
        )

    return reporte


def _print_resumen(r: dict) -> None:
    if "error" in r:
        print(f"❌ {r['error']}")
        return

    print("=" * 70)
    print(f"  EVALUACIÓN PRE-DEPLOY · {r['input_dir']}")
    print("=" * 70)
    print(f"  Total procesados : {r['total']}")
    print(f"  OK               : {r['ok']:3d}  ({r['pct_ok']:.1f}%)")
    print(f"  QUARANTINE       : {r['quarantine']:3d}")
    print(f"  REJECTED         : {r['rejected']:3d}")
    print(f"  Proceso completo : {r['pct_usable']:.1f}%  (OK + QUARANTINE, sin crashes)")
    print(f"  Tiempo           : {r['elapsed_sec']:.1f}s")
    print()
    print("  Faltantes en QUARANTINE:")
    for k, v in sorted(r["faltantes_quarantine"].items(), key=lambda x: -x[1]):
        print(f"    - {k:18s}: {v}")
    print()
    print("  Por ruta de ingestión:")
    for ruta, vals in sorted(r["por_ruta"].items()):
        sub_total = sum(vals.values())
        ok_sub = vals.get("ok", 0)
        print(f"    {ruta:14s}  OK={ok_sub}/{sub_total}  {dict(vals)}")
    print()
    print("  Por doc_type:")
    for dt, vals in sorted(r["por_doc_type"].items()):
        sub_total = vals.get("total", 0)
        ok_sub = vals.get("ok", 0)
        print(f"    {str(dt):28s}  OK={ok_sub}/{sub_total}  {dict(vals)}")
    print()
    print("  Por extensión:")
    for ext, n in sorted(r["por_extension"].items(), key=lambda x: -x[1]):
        print(f"    {ext:8s}  {n}")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluación pre-deploy CapturadorM3")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("documentos_ingresados"),
        help="Carpeta con documentos a evaluar",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output/eval_reporte.json"),
        help="Ruta del JSON con el reporte detallado",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    reporte = evaluar(args.input, args.out)
    _print_resumen(reporte)
    print(f"\n  Reporte JSON: {args.out}")

    # Exit code útil para CI
    pct = reporte.get("pct_ok", 0)
    if pct >= 95:
        return 0
    if pct >= 80:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
