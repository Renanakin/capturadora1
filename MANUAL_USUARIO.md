# Manual de Usuario — CapturadorM3

> **OCR Tributario Chileno · DTE → Excel**
> Convierte boletas, facturas, notas de crédito y comprobantes chilenos en planillas Excel listas para entregar a contabilidad.

Este manual tiene **dos partes**:

- **Parte 1 — Usuario básico**: si solo quieres subir tus documentos y bajar el Excel.
- **Parte 2 — Desarrollador**: si vas a leer o modificar el código.

---

# 🧑 Parte 1 — Manual del Usuario Básico

## 1.1 ¿Qué hace CapturadorM3?

Toma tus **boletas y facturas** (PDF, fotos de celular, escaneos) y extrae automáticamente:

| Campo | Ejemplo |
|---|---|
| Fecha de emisión | `2025-12-20` |
| RUT del emisor | `90.635.000-9` |
| Número de documento (folio) | `53880422` |
| Proveedor / Razón social | `Telefónica Chile S.A.` |
| Total (CLP) | `18.521` |
| Mes | `2025-12` |

Y te entrega una planilla Excel lista para subir a tu sistema de rendición.

> 🇲🇽/🇨🇱 **Diseñado para documentos chilenos**: boletas electrónicas, facturas afectas/exentas, notas de crédito, guías de despacho, cédulas de identidad, y también facturas extranjeras (Google Play, AWS, etc.) que se marcan como `EXTRANJERO`.

---

## 1.2 Hay 3 formas de usarlo

### Opción A — Interfaz web (la más fácil)

1. Abre tu navegador en **http://127.0.0.1:8000/**
2. Verás 4 pasos: **Cargar → Procesar → Revisar → Entregar**
3. **Paso 1**: arrastra tus archivos a la zona punteada (o haz click)
4. **Paso 2**: click en **⚡ Procesar ahora** y espera la barra de progreso
5. **Paso 3**: revisa la tabla; las filas en ámbar requieren tu atención
6. **Paso 4**: click en **⬇ Descargar Excel de rendición**

> Modo asíncrono (checkbox): si lo activas, el procesamiento se hace en segundo plano vía worker. Útil para lotes grandes (>20 archivos).

### Opción B — Línea de comandos (batch)

Si tienes muchos archivos en una carpeta, sin abrir el navegador:

```powershell
cd G:\DESARROLLOS\CAPTURADORM3
.\.venv311\Scripts\python.exe -m ocr_tributario cli --input documentos_ingresados --verbose
```

Resultado: `output/Rendicion_Gastos_OCR_2026-07.xlsx` (o `.csv`).

### Opción C — API REST (para integrar con otro sistema)

```bash
# Subir un PDF
curl -X POST "http://127.0.0.1:8000/api/v1/ocr/upload" \
     -F "file=@mi_boleta.pdf"

# Procesar por lotes
curl -X POST "http://127.0.0.1:8000/api/v1/ocr/batch" \
     -F "files=@boleta1.pdf" -F "files=@boleta2.jpg"
```

Documentación interactiva: **http://127.0.0.1:8000/docs** (Swagger).

---

## 1.3 ¿Qué archivos acepta?

| Tipo | Extensiones | Notas |
|---|---|---|
| PDF | `.pdf` | PDFs nativos (con texto) **y** PDFs escaneados |
| Imágenes | `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, `.tiff` | Fotos de celular, escaneos, capturas |

Tamaño máximo: **100 archivos por lote**. No hay límite de tamaño por archivo (depende de tu RAM).

---

## 1.4 ¿Qué significan los estados?

| Estado | Color | Significado | ¿Sube al Excel? |
|---|---|---|---|
| **OK** | Verde | Tiene fecha + RUT + total → datos completos | ✅ Sí, hoja "Procesados" |
| **QUARANTINE** | Ámbar | Faltan algunos campos (ej: no se pudo leer el RUT) | ⚠️ Hoja "Revisión Manual" |
| **REJECTED** | Rojo | Excepción no recuperable (archivo corrupto) | ❌ Hoja "Revisión Manual" |

**No te preocupes si ves ámbar** — el sistema es conservador: si tiene duda sobre un campo, lo manda a revisión en vez de inventar datos.

---

## 1.5 El Excel de salida

**`output/Rendicion_Gastos_OCR_YYYY-MM.xlsx`** con 2 hojas:

### Hoja "Procesados" (49 documentos OK en el último test)
9 columnas preestablecidas, en este orden:

| # | Columna | Ejemplo |
|---|---|---|
| 1 | Archivo | `boleta-1.png` |
| 2 | Mes | `2025-12` |
| 3 | Fecha | `2025-12-20` |
| 4 | Nro Boleta Factura | `53880422` |
| 5 | PROVEEDOR | `Telefónica Chile S.A.` |
| 6 | RUT | `90.635.000-9` |
| 7 | Total | `18.521` |
| 8 | Descripción del gasto | (vacío, lo llenas tú) |
| 9 | Observaciones | (vacío, lo llenas tú) |

- **Total** viene como número nativo de Excel (formato `#,##0`) → se ve `18.521` con separador de miles y se puede sumar directo.
- **Fecha** viene como fecha nativa (`yyyy-mm-dd`) → sirve para filtros y ordenamiento.

### Hoja "Revisión Manual" (3 documentos en quarantine)
Mismas 9 columnas + `estado` + `motivo_revision` al inicio. Las filas están resaltadas en rojo claro.

Ejemplo de motivo: `Faltan: rut_emisor, fecha_emision, total | Completitud: 67%`

---

## 1.6 ¿Y el CSV?

Si prefieres CSV, el script genera:
- `output/Rendicion_Gastos_OCR.csv` — solo registros OK, 9 columnas
- `output/Rendicion_Gastos_OCR_revision.csv` — incluye estado + motivo, todos los registros

Codificación: **UTF-8 con BOM** (acentos correctos al abrir en Excel). Delimitador: **`;`** (estándar chileno).

---

## 1.7 Cómo arrancar el sistema desde cero

### Requisitos
- Windows 10/11
- Python 3.11+ (en este equipo: `.venv311`)
- Tesseract OCR instalado en `C:\Program Files\Tesseract-OCR\`
- (Opcional) Redis si quieres modo asíncrono

### Pasos

```powershell
# 1. Abrir PowerShell en la carpeta del proyecto
cd G:\DESARROLLOS\CAPTURADORM3

# 2. Activar el entorno virtual
.\.venv311\Scripts\Activate.ps1

# 3a. Opción A: levantar la interfaz web
python -m ocr_tributario api --port 8000
# → Abre http://127.0.0.1:8000/

# 3b. Opción B: procesar por CLI
python -m ocr_tributario cli --input mi_carpeta --verbose
# → Genera output/Rendicion_Gastos_OCR_YYYY-MM.xlsx
```

### Si quieres parar el servidor
En la misma consola: `Ctrl+C`. O desde otra consola: `Get-Process python | Stop-Process`.

---

## 1.8 Validar un RUT a mano

Si tienes un RUT y quieres verificar si es válido antes de meterlo al sistema:

1. Click en **🔍 Validar RUT** (esquina superior derecha de la interfaz)
2. Escribe el RUT (con o sin formato, con o sin puntos/guión)
3. Click en **Validar**

Implementa el algoritmo **Módulo 11** del SII chileno:
- `12.345.678-5` → ✅ Válido
- `12.345.678-9` → ❌ DV incorrecto

---

## 1.9 Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| "Tesseract no encontrado" | Tesseract no instalado | Instalar desde https://github.com/UB-Mannheim/tesseract/wiki |
| Casi todos los documentos quedan en QUARANTINE | PDF escaneado de baja calidad | Escanear a 300 DPI mínimo |
| El RUT se extrae mal | El OCR no leyó bien el RUT (común en fotos borrosas) | Revisar manualmente en la hoja "Revisión Manual" |
| "Connection refused" en la UI | La API no está corriendo | Arrancar con `python -m ocr_tributario api` |
| Modo asíncrono no funciona | Redis no está corriendo | Iniciar Redis o usar modo síncrono (sin checkbox) |

---

# 👨‍💻 Parte 2 — Manual del Desarrollador

Esta parte explica la arquitectura, cómo está organizado el código, y cómo extenderlo.

---

## 2.1 Visión general de la arquitectura

```
                        ┌──────────────────────────┐
                        │   Frontend (vanilla JS)  │
                        │  index.html + app.js     │
                        └────────────┬─────────────┘
                                     │ HTTP
                        ┌────────────▼─────────────┐
                        │   FastAPI (api/main.py)  │
                        │   /api/v1/ocr/...        │
                        │   /api/v1/jobs/...       │
                        └────────────┬─────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
   ┌──────────▼─────────┐  ┌─────────▼────────┐  ┌──────────▼────────┐
   │  Ingestion         │  │  Orchestrator     │  │  Exporters         │
   │  scanner.py        │  │  pipeline.py      │  │  excel_writer.py   │
   │  router.py         │  │  hitl.py          │  │  csv_writer.py     │
   │  magic_bytes.py    │  │                   │  │                    │
   └──────────┬─────────┘  └─────────┬────────┘  └────────────────────┘
              │                      │
              │              ┌───────┴────────────────────┐
              │              │  Extractors                │
              │              │  pdf_native.py             │
              │              │  image_fallback.py         │
              │              │  anchors.py                │
              │              │  ocr_tesseract.py          │
              │              └───────┬────────────────────┘
              │                      │
              │              ┌───────▼────────────────────┐
              │              │  Preprocessing              │
              │              │  opencv_pipeline.py         │
              │              │  hsv_segmenter.py           │
              │              └───────┬────────────────────┘
              │                      │
              │              ┌───────▼────────────────────┐
              │              │  Services                   │
              │              │  classify.py                │
              │              │  ocr_paddle.py              │
              │              │  ocr_tesseract.py           │
              │              │  parse_dte.py               │
              │              │  parse_cedula.py            │
              │              │  template_engine.py         │
              │              │  donut_kie.py               │
              │              └───────┬────────────────────┘
              │                      │
              │              ┌───────▼────────────────────┐
              │              │  Validators                 │
              │              │  regex_patterns.py          │
              │              │  rut.py                     │
              │              │  normalizers.py             │
              │              └─────────────────────────────┘
              │
   ┌──────────▼─────────┐
   │  Models            │
   │  invoice.py        │
   │  cedula.py         │
   └────────────────────┘
```

**Flujo en una línea**: `archivo → ingestion → router → extractors → ocr services → parsers → modelo → exporter → Excel/CSV`

---

## 2.2 Estructura de carpetas

```
G:\DESARROLLOS\CAPTURADORM3\
├── config/
│   └── settings.yaml              # Configuración externa (rutas, HSV, OCR, columnas Excel)
├── documentos_ingresados/         # Carpeta de entrada (batch mode)
├── frontend/
│   ├── index.html                 # SPA 4 pasos
│   ├── app.css
│   └── app.js                     # Lógica de UI (vanilla JS)
├── logs/                          # Logs rotados
├── output/                        # Excel/CSV generados
├── quarantine/                    # Excels de revisión HITL
├── scripts/                       # Scripts auxiliares (PowerShell + Python)
│   ├── env_helper.ps1
│   ├── run_api.ps1
│   ├── run_batch.ps1
│   ├── run_redis.ps1
│   ├── run_worker.ps1
│   ├── eval_documentos.py         # Evaluación pre-deploy
│   ├── export_results.py          # Genera Excel+CSV
│   └── generate_predeploy_report.py
├── src/ocr_tributario/            # Paquete principal
│   ├── __main__.py                # Entry-point: api/worker/cli
│   ├── api/                       # FastAPI
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── ocr.py             # POST /ocr/upload, /ocr/batch
│   │   │   ├── jobs.py            # GET/POST /jobs/...
│   │   │   └── utils.py
│   │   └── schemas.py
│   ├── config/                    # Configuración (Pydantic)
│   │   ├── loader.py              # load_settings()
│   │   ├── schema.py              # Settings, PathsConfig, ExcelConfig, etc.
│   │   └── templates.yaml         # Templates auto-aprendizaje
│   ├── exporters/
│   │   ├── excel_writer.py        # 2 hojas, formato nativo int/date
│   │   └── csv_writer.py          # UTF-8 BOM, delimitador ;
│   ├── extractors/                # Extracción por ruta
│   │   ├── pdf_native.py          # Texto embebido en PDF (pdfplumber)
│   │   ├── image_fallback.py      # Render PDF + OCR
│   │   ├── ocr_tesseract.py       # Tesseract standalone
│   │   └── anchors.py             # Extracción por anclas visuales
│   ├── ingestion/                 # Entrada
│   │   ├── scanner.py             # scan_directory()
│   │   ├── router.py              # route() → pdf_native | pdf_image | image
│   │   └── __init__.py
│   ├── models/                    # Dataclasses
│   │   ├── invoice.py             # InvoiceRecord (estado OK/QUARANTINE/REJECTED)
│   │   └── cedula.py
│   ├── orchestrator/              # Flujo principal
│   │   ├── pipeline.py            # process_one() / process_directory()
│   │   └── hitl.py                # write_quarantine_excel()
│   ├── preprocessing/             # OpenCV
│   │   ├── opencv_pipeline.py     # load_image, preprocess_image
│   │   └── hsv_segmenter.py       # Detección recuadro rojo SII
│   ├── services/                  # Lógica de negocio
│   │   ├── classify.py            # DocumentType enum + classify_document()
│   │   ├── ocr_paddle.py          # PaddleOCR
│   │   ├── ocr_tesseract.py       # Tesseract
│   │   ├── parse_dte.py           # DTE → DTEFields
│   │   ├── parse_cedula.py
│   │   ├── template_engine.py     # Auto-aprendizaje HITL
│   │   └── donut_kie.py           # Rescate con Donut (KIE)
│   ├── utils/
│   ├── validators/                # Regex y normalización
│   │   ├── regex_patterns.py      # extract_date/total/folio/rut
│   │   ├── rut.py                 # validate_rut (Módulo 11)
│   │   └── normalizers.py         # extract_provider
│   └── workers/                   # arq workers (async)
│       └── (WorkerSettings)
├── tests/                         # pytest
│   ├── test_api.py
│   ├── test_hsv_segmenter.py
│   ├── test_regex_patterns.py
│   ├── test_rut_validator.py
│   └── test_smoke.py
├── uploads/                       # Archivos subidos vía API
├── pyproject.toml
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── README.md
└── MANUAL_USUARIO.md              # ← este archivo
```

---

## 2.3 El flujo de procesamiento, paso a paso

Tomemos como ejemplo `boleta-1.png` (boleta electrónica de un proveedor chileno).

### Paso 1 — Ingestion (`ingestion/scanner.py` + `router.py`)

`scan_directory(input_dir)` recorre `documentos_ingresados/` y crea una lista de `DocumentInput(path, file_type)`. `file_type` se detecta por magic bytes (`utils/magic_bytes.py`).

`router.route(doc)` decide:
- **PDF con texto embebido** → `pdf_native` (rápido, sin OCR)
- **PDF sin texto** (escaneado) → `pdf_image` (render + OCR)
- **Imagen** (jpg/png/webp/tiff) → `image` (OCR directo)

```python
# router.py
def route(doc):
    if doc.file_type == "pdf":
        if has_extractable_text(doc.path):
            return "pdf_native"
        return "pdf_image"
    if doc.file_type == "image":
        return "image"
    return "unknown"
```

### Paso 2 — Preprocesamiento (solo imágenes, `preprocessing/`)

```python
# pipeline.py
img = load_image(source_path)                    # OpenCV lee
hsv_crop_info = extract_sii_red_box(img, ...)    # ¿hay recuadro rojo SII?
pre = preprocess_image(img)                      # resize, grayscale, blur
if not hsv_crop_info:
    pre = adaptive_threshold(pre)               # umbralizado para térmicas
```

`extract_sii_red_box` usa HSV (rangos configurables en `settings.yaml`) para aislar el recuadro rojo del SII, lo que da una pista adicional sobre el RUT y folio.

### Paso 3 — OCR dual (`services/ocr_paddle.py` + `ocr_tesseract.py`)

```python
# pipeline.py → _run_dual_ocr
paddle_result = OCRPaddle(lang="es").read_with_confidence_threshold(pre, min_score=0.3)
tess_result = OCRTesseract(...).read_multi_psm(pre, settings.ocr)
merged = _merge_dual_ocr(paddle_result, tess_result, settings)
```

¿Por qué dos motores?
- **PaddleOCR** (neuronal) suele ser mejor en texto impreso, pero a veces alucina.
- **Tesseract** es más conservador y rápido.
- `_merge_dual_ocr` puntúa cada output (RUT? fecha? total? longitud?) y se queda con el mejor texto, **concatenando ambos** para que el parser no se pierda ningún campo.

### Paso 4 — Clasificación (`services/classify.py`)

```python
doc_type = classify_document(ocr_result)
```

Heurística de keywords + tolerancia a typos OCR (normalización de `ELECTRONCA` → `ELECTRONICA`):

| Tipo | Keywords | Score |
|---|---|---|
| FACTURA_ELECTRONICA | "FACTURA ELECTRONICA" | 10 |
| BOLETA_ELECTRONICA | "BOLETA ELECTRONICA" | 10 |
| NOTA_CREDITO | "NOTA DE CREDITO" | 10 |
| CEDULA | "CEDULA DE IDENTIDAD" | 10 |
| INVOICE_EXTRANJERA | "INVOICE", "RECEIPT", "GOOGLE PLAY" | 10 |
| DTE_GENERICO | 2+ de {RUT, FOLIO, SII} | — |
| DESCONOCIDO | (ninguno matchea) | 0 |

### Paso 5 — Template matching (`services/template_engine.py`)

Si el texto coincide con un proveedor conocido (cargado desde `config/templates.yaml`), se extraen campos con reglas custom:

```yaml
proveedores:
  - nombre: "Google Play"
    keywords_identificacion: ["Google Play", "Play Store"]
    rut_defecto: "EXTRANJERO"
    reglas:
      total: "regex: Total\\s*\\$?([\\d\\.]+)"
      fecha: "regex: del (\\d{1,2} [a-z]{3} \\d{4})"
```

El archivo `templates.yaml` es editable y se puede entrenar con un supervisor (HITL). Hoy tiene solo Google Play, pero es extensible.

### Paso 6 — Parsing (`services/parse_dte.py`)

Si no hay match de template, se usa `parse_dte_fields(doc_type, ocr_result)` que llena un `DTEFields` con:

```python
DTEFields(
    doc_type=FACTURA_ELECTRONICA,
    folio=53880422,
    rut_emisor="90.635.000-9",
    razon_social="Telefónica Chile S.A.",
    fecha_emision=date(2025, 12, 20),
    total=18521,
    ...
)
```

Cada campo se extrae con:
- `extract_date(text)` → regex multi-formato
- `extract_rut(text)` → RUT_INLINE → RUT_FALLBACK → RUT_NO_DV
- `extract_total(text)` → regex tolerante a OCR
- `extract_folio(text)` → N°, NRO, "factura N"
- `extract_provider(text)` → heurística de razón social

### Paso 7 — Donut rescue (opcional, `services/donut_kie.py`)

Si el record queda en `QUARANTINE` (faltan campos), el pipeline intenta un **rescate con Donut** (modelo KIE neuronal). Si Donut extrae un total o fecha que faltaba, se rellena.

```python
if rec.estado == "QUARANTINE":
    ai_data = extract_with_donut(source_path)
    if not rec.total and "total_price" in ai_data:
        rec.total = _parse_money(ai_data["total_price"])
    if not rec.fecha and "date" in ai_data:
        rec.fecha = extract_date(ai_data["date"]).isoformat()
    if rec.is_valid_for_excel():
        rec.estado = "OK"
        rec.motivo_revision = "Rescatado por IA (Donut)"
```

### Paso 8 — Asignación de estado (`models/invoice.py`)

```python
def is_valid_for_excel(self) -> bool:
    """Un record es OK si tiene fecha + RUT + total (mínimo para subir)."""
    return bool(self.fecha and self.rut and self.total is not None)
```

- Si todo lo crítico está → `OK`
- Si falta algo → `QUARANTINE` (con motivo)
- Si hubo excepción → `REJECTED` (con stacktrace en el motivo)

---

## 2.4 Los modelos de datos

`src/ocr_tributario/models/invoice.py`:

```python
@dataclass
class InvoiceRecord:
    archivo_origen: str                # Nombre del archivo
    mes: str | None                    # "2025-12" (YYYY-MM)
    fecha: str | None                  # "2025-12-20" (YYYY-MM-DD)
    nro_documento: int | None          # 53880422
    proveedor: str | None              # "Telefónica Chile S.A."
    rut: str | None                    # "90.635.000-9"
    total: int | None                  # 18521 (CLP entero)
    descripcion: str | None            # Libre, lo llena el usuario
    observaciones: str | None          # Libre
    estado: "OK" | "QUARANTINE" | "REJECTED"
    motivo_revision: str | None
    ruta_extraccion: str | None        # "pdf_native" | "image_dual" | "pdf_image"
    raw_text: str | None               # Texto OCR completo (para debug)
    doc_type: str | None               # "factura_electronica", etc.
    ocr_engine: str | None             # "dual_paddle_priority", etc.
    ocr_avg_score: float | None
    completeness: float | None         # 0.0–1.0
```

---

## 2.5 La configuración externa (`config/settings.yaml`)

Toda la config editable sin tocar código está acá:

```yaml
paths:
  input_dir: "documentos_ingresados"
  output_dir: "output"
  tesseract_cmd: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
  tessdata_prefix: "C:\\Users\\Tranquilidad\\.tessdata\\"

hsv_red:                        # Rangos HSV para el recuadro SII
  lower1: [0, 70, 50]
  upper1: [10, 255, 255]
  lower2: [170, 70, 50]
  upper2: [179, 255, 255]
  min_area: 5000
  aspect_ratio: [1.5, 3.5]
  padding: 10

ocr:
  lang: "spa"
  psm: 3
  dpi: 300

excel:                          # Columnas preestablecidas
  template_columns:
    - Archivo
    - Mes
    - Fecha
    - Nro Boleta Factura
    - PROVEEDOR
    - RUT
    - Total
    - Descripción del gasto
    - Observaciones
  sheet_procesados: "Procesados"
  sheet_revision: "Revisión Manual"
  freeze_header: true
```

Para cambiar las columnas del Excel: edita `template_columns` y reinicia la API. **Nada más.**

---

## 2.6 Cómo extender el sistema

### Agregar un nuevo tipo de documento

1. Abre `services/classify.py`
2. Agrega un valor al enum:
   ```python
   class DocumentType(str, Enum):
       FACTURA_ELECTRONICA = "factura_electronica"
       ...
       RECIBO_HONORARIOS = "recibo_honorarios"   # ← nuevo
   ```
3. Agrega keywords:
   ```python
   _KEYWORDS[DocumentType.RECIBO_HONORARIOS] = {
       "RECIBO DE HONORARIOS": 10,
       "BOLETA DE HONORARIOS": 8,
   }
   ```
4. Define campos requeridos en `services/parse_dte.py`:
   ```python
   DocumentType.RECIBO_HONORARIOS: ["folio", "rut_emisor", "fecha_emision", "total", "bruto", "retencion"],
   ```
5. Agrega tests en `tests/`.

### Agregar un proveedor al motor de plantillas

Edita `src/ocr_tributario/config/templates.yaml`:

```yaml
proveedores:
  - nombre: "MiProveedor"
    keywords_identificacion: ["MiProveedor", "MiProv SpA"]
    rut_defecto: "76.123.456-7"
    reglas:
      total: "regex: TOTAL\\s*\\$?([\\d\\.]+)"
      fecha: "regex: Fecha:\\s*(\\d{2}/\\d{2}/\\d{4})"
      folio: "regex: N[°ºo\\.]?\\s*(\\d+)"
```

Listo. No hay que tocar código (excepto si el regex de la regla necesita una función custom).

### Mejorar la extracción de un campo

Si notas que un campo (ej. RUT) se extrae mal en muchos documentos:

1. Ve a `validators/regex_patterns.py`
2. Agrega un nuevo patrón al inicio de la lista (se prueban en orden)
3. Agrega un test en `tests/test_regex_patterns.py`
4. Corre `pytest tests/`

### Re-entrenar el OCR

El PaddleOCR usa el modelo `es` por defecto (español). Si quieres otro idioma:
- `services/ocr_paddle.py` línea ~56: `OCRPaddle(lang='es')` → cambiar a `'en'`, `'es+en'`, etc.

---

## 2.7 Tests

```powershell
# Suite completa
.\.venv311\Scripts\python.exe -m pytest tests/

# Solo un archivo
.\.venv311\Scripts\python.exe -m pytest tests/test_regex_patterns.py -v

# Cobertura (necesita pytest-cov)
.\.venv311\Scripts\python.exe -m pytest tests/ --cov=ocr_tributario
```

Estructura de los tests:

| Archivo | Qué cubre |
|---|---|
| `test_api.py` | Endpoints FastAPI (root + health) |
| `test_hsv_segmenter.py` | Detector de recuadro rojo |
| `test_regex_patterns.py` | Extracción de fecha, total, folio, RUT |
| `test_rut_validator.py` | Validador Módulo 11 |
| `test_smoke.py` | Importación del paquete + settings |

Cuando agregues un extractor/parser, **agrega su test** con al menos 3 casos: positivo, negativo, y borde.

---

## 2.8 Endpoints del API

| Método | Endpoint | Función |
|---|---|---|
| GET | `/` | Frontend (SPA) |
| GET | `/docs` | Swagger UI interactivo |
| GET | `/api/v1/` | Metadata del servicio |
| GET | `/api/v1/health` | Health check (status, redis, db) |
| POST | `/api/v1/ocr/upload` | Sube 1 archivo, devuelve `DTEResponseSchema` |
| POST | `/api/v1/ocr/batch` | Sube N archivos, devuelve lista |
| POST | `/api/v1/ocr/process-directory` | Procesa toda la carpeta `documentos_ingresados` |
| POST | `/api/v1/ocr/rut/validate` | Valida un RUT (Módulo 11) |
| GET | `/api/v1/jobs/{job_id}` | Estado de un job async |
| GET | `/api/v1/jobs/` | Listar jobs |
| GET | `/api/v1/jobs/{job_id}/export` | Descargar Excel de un job |

Ver `src/ocr_tributario/api/routes/ocr.py` y `jobs.py` para implementación.

---

## 2.9 Logging y debugging

- **Logs estructurados**: `loguru` con rotación. Salida en consola + `logs/`.
- **Niveles**: `DEBUG` (verbose), `INFO` (default), `WARNING` (raro), `ERROR` (fallo recuperable).
- **Para debug**:
  ```powershell
  python -m ocr_tributario cli --input mi_doc --verbose
  ```
  o en Python:
  ```python
  logger.add("logs/debug.log", level="DEBUG", rotation="10 MB")
  ```

- **Para ver el `raw_text` de un documento** (lo que leyó el OCR), revisa el campo `raw_text` en el JSON de la API, o mira el `output/eval_reporte.json` después de correr `python -m scripts.eval_documentos`.

---

## 2.10 Despliegue

### Local (desarrollo)
```powershell
python -m ocr_tributario api --port 8000
```

### Docker
```powershell
docker compose up -d
```
Ver `docker-compose.yml` y `Dockerfile`. El compose levanta API + worker + Redis.

### Producción
- Configurar `config/settings.yaml` con rutas de producción
- Usar un process manager (systemd, supervisord) o un reverse proxy (nginx)
- Montar volumen persistente para `output/`, `quarantine/`, `logs/`, `uploads/` y la DB SQLite
- Habilitar HTTPS en el proxy
- Configurar backups de `capturador_db.sqlite3`

---

## 2.11 Decisiones de diseño

| Decisión | Razón |
|---|---|
| **PaddleOCR + Tesseract dual** | PaddleOCR es más preciso en texto impreso, Tesseract es más conservador. La combinación reduce falsos positivos. |
| **pdfplumber primero para PDF** | 10× más rápido que OCR para PDFs con texto embebido. |
| **Módulo 11 para RUT** | Algoritmo oficial del SII chileno. Detecta RUTs mal tipeados automáticamente. |
| **HSV segmenter para recuadro SII** | Aísla el RUT y folio de DTEs incluso cuando el resto del doc es de baja calidad. |
| **Donut como rescue** | Último recurso antes de marcar como QUARANTINE. Modelo KIE neuronal entrenado en facturas. |
| **Templates con auto-aprendizaje** | Proveedores recurrentes (Google Play, AWS) → el sistema aprende el patrón y lo extrae directo. |
| **CSV UTF-8-BOM con `;`** | Estándar chileno/europeo. Excel lo abre sin problemas de encoding. |
| **Quarantine en vez de inventar** | Si falta un campo crítico, el sistema NO adivina. Lo manda a revisión. La planilla queda 100% real. |

---

## 2.12 Glosario de términos

| Término | Significado |
|---|---|
| **DTE** | Documento Tributario Electrónico (SII). incluye facturas, boletas, NC, guías. |
| **Módulo 11** | Algoritmo del SII para validar el dígito verificador del RUT. |
| **OCR** | Optical Character Recognition. Convierte imagen → texto. |
| **KIE** | Key Information Extraction. Extrae campos estructurados de documentos. |
| **HSV** | Espacio de color (Hue, Saturation, Value). Útil para detectar colores específicos (recuadro rojo). |
| **PSM** | Page Segmentation Mode de Tesseract. Define cómo se segmenta la página antes de OCR. |
| **HITL** | Human-In-The-Loop. Flujo donde un humano corrige los casos difíciles y el sistema aprende. |
| **Pre-deploy** | Verificación final antes de pasar a producción. |
| **Quarantine** | Estado "en espera de revisión humana". No es un error, es un caso que necesita ojos humanos. |

---

## 2.13 Próximos pasos sugeridos

- [ ] Subir el modelo Donut a un server dedicado (es lento en CPU)
- [ ] Implementar cola de revisión web (HITL visual)
- [ ] Agregar soporte para más idiomas (inglés, portugués)
- [ ] Exportador a PDF (además de Excel/CSV)
- [ ] Integración directa con SII (API del SII para validar DTE)
- [ ] Dashboard de métricas históricas
- [ ] Modo "carpeta vigilada" (auto-procesa nuevos archivos)

---

## 2.14 Contacto y contribución

- **Repo**: `G:\DESARROLLOS\CAPTURADORM3`
- **Issues**: hablar con el equipo de CapturadorM3
- **Reglas de contribución** (del `README.md`):
  1. Cero hardcoding (toda config en `.env` o `settings.yaml`)
  2. Cero `print()` en producción (usar `loguru`)
  3. Tests para todo lo crítico
  4. Naming semántico (las carpetas explican el porqué)

---

**¡Listo! Ya tienes todo para usar el sistema como usuario o para meterle mano al código.** 🚀

> Si tienes dudas del sistema, abre el navegador en http://127.0.0.1:8000/ y prueba la UI.
> Si tienes dudas del código, empieza por `src/ocr_tributario/orchestrator/pipeline.py` — es el orquestador central.
