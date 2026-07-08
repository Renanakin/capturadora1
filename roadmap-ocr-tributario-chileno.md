# Roadmap de Implementación: Sistema OCR Tributario Chileno (100% Programático)

**Proyecto:** `capturador_datos_v2`
**Stack:** Python 3.11+ · pdfplumber · OpenCV · PyTesseract · pandas · openpyxl
**Filosofía:** Cero LLMs, cero APIs de pago, cero latencia de red. Todo on‑premises, determinista y auditable.
**Autor del informe:** Mavis (asistente técnico)
**Fecha:** 2026-07-08

---

## 0. Resumen Ejecutivo

El sistema procesa **PDFs nativos** e **imágenes (JPEG/PNG)** de facturas/boletas chilenas y mapea los datos extraídos a las columnas exactas de la planilla de rendición de gastos de la empresa:

```
Mes | Fecha | Nro Boleta Factura | PROVEEDOR | RUT | Total | + metadatos HITL
```

El pipeline opera en **5 fases desacopladas**:

```
[Ingesta] → [Preprocesamiento OpenCV] → [Segmentación HSV recuadro SII] → [Motor OCR/pdfplumber] → [Validación + RegEx] → [Excel]
```

**Resultado esperado:** `Rendicion_Gastos_OCR_<periodo>.xlsx` con tasa de éxito > 95% en PDFs nativos y > 80% en imágenes de calidad media, más una **cola de revisión HITL** para los casos fallidos.

---

## 1. Análisis Crítico del Diseño Propuesto

### 1.1 Lo que está bien diseñado

| Aspecto | Por qué funciona |
|---|---|
| **Bifurcación PDF nativo ↔ imagen** | Evita OCR innecesario en PDFs con capa de texto. Precisión 100% vs ~85% OCR. |
| **Segmentación HSV del recuadro rojo SII** | Reduce drásticamente el área de OCR. Es el único dato "digno de confianza visual" en una factura chilena. |
| **Validador RUT Módulo 11 local** | Filtra falsos positivos del OCR antes de contaminar la planilla. |
| **Decisión de NO usar LLMs** | Latencia, costo, alucinaciones y privacidad. Totalmente acertado para datos estructurados repetitivos. |

### 1.2 Lo que hay que endurecer antes de producción

| Riesgo | Mitigación obligatoria |
|---|---|
| Rangos HSV del rojo hardcodeados sin calibrar | Calibrar con 10–20 facturas reales y guardar rangos en `config.yaml` |
| `page.to_image()` no maneja multipágina | Implementar loop `for page in pdf.pages` y concatenar resultados |
| Tesseract no instalado en Windows | Incluir guía de instalación del binario + variable `pytesseract.pytesseract.tesseract_cmd` |
| Sin logging estructurado | Agregar `loguru` o `logging` con JSON por documento procesado |
| Sin reintentos ni cuarentena HITL | Carpeta `quarantine/` + Excel paralelo `revisar_manual.xlsx` |
| Encoding de RUT con `K` mayúscula vs minúscula | Normalizar `.upper()` antes de comparar (ya está en el código, validar) |
| Fechas ambiguas DD/MM vs MM/DD | Configurar locale `es_CL` y validar rango mes ∈ [1,12] |
| Multiprocessing no contemplado | Usar `concurrent.futures.ProcessPoolExecutor` para escalar |

---

## 2. Prerrequisitos del Entorno

### 2.1 Sistema (Windows 10/11)

| Componente | Versión mínima | Comando de verificación |
|---|---|---|
| Python | 3.11.x | `python --version` |
| Tesseract OCR | 5.3+ con paquete `spa` | `tesseract --version` y `tesseract --list-langs` |
| Poppler (para `pdf2image` fallback) | 24.x | `pdftoppm -v` |
| Git | 2.40+ | `git --version` |

**Instalación Tesseract en Windows (CRÍTICO):**
1. Descargar instalador desde [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Durante instalación, **marcar el idioma Spanish (`spa`)**
3. Agregar `C:\Program Files\Tesseract-OCR` al `PATH`
4. En el código, fijar:
   ```python
   pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

### 2.2 Dependencias Python

`requirements.txt` propuesto:
```
pdfplumber==0.11.4
pypdfium2==4.30.0          # renderizado PDF -> imagen de fallback
opencv-python==4.10.0.84
pytesseract==0.3.13
Pillow==10.4.0
pandas==2.2.3
openpyxl==3.1.5
numpy==1.26.4
pydantic==2.9.2            # validación de esquemas
loguru==0.7.2              # logging estructurado
pyyaml==6.0.1              # configuración externa
python-dotenv==1.0.1
tqdm==4.66.5               # barras de progreso
pytest==8.3.3              # testing
```

**Instalación:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Estructura del Proyecto Recomendada

```
capturador_datos_v2/
│
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml                  # opcional, para packaging
│
├── config/
│   └── settings.yaml               # rutas, rangos HSV, umbrales, flags
│
├── src/
│   └── ocr_tributario/
│       ├── __init__.py
│       ├── __main__.py             # entrypoint: python -m ocr_tributario
│       │
│       ├── config/
│       │   ├── loader.py           # carga settings.yaml
│       │   └── schema.py           # Pydantic models
│       │
│       ├── ingestion/
│       │   ├── router.py           # detecta magic bytes y enruta
│       │   └── scanner.py          # recorre directorios
│       │
│       ├── preprocessing/
│       │   ├── opencv_pipeline.py  # bilateral, adaptive threshold, deskew
│       │   └── hsv_segmenter.py    # aislamiento recuadro SII
│       │
│       ├── extractors/
│       │   ├── pdf_native.py       # pdfplumber + crop por coordenadas
│       │   ├── ocr_tesseract.py    # PyTesseract + whitelist
│       │   └── image_fallback.py   # PDF escaneado -> imagen -> OCR
│       │
│       ├── validators/
│       │   ├── rut.py              # Módulo 11
│       │   ├── regex_patterns.py   # fecha, monto, folio
│       │   └── normalizers.py      # formato canónico
│       │
│       ├── models/
│       │   └── invoice.py          # dataclass / Pydantic del documento
│       │
│       ├── orchestrator/
│       │   ├── pipeline.py         # coordina las 5 fases
│       │   └── hitl.py             # cuarentena + cola revisión
│       │
│       ├── exporters/
│       │   └── excel_writer.py     # -> Rendicion_Gastos_OCR_*.xlsx
│       │
│       └── utils/
│           ├── logging.py          # loguru setup
│           └── magic_bytes.py      # detección tipo archivo
│
├── tests/
│   ├── unit/
│   │   ├── test_rut_validator.py
│   │   ├── test_regex_patterns.py
│   │   └── test_hsv_segmenter.py
│   ├── integration/
│   │   ├── test_pdf_native.py
│   │   └── test_image_flow.py
│   └── fixtures/
│       ├── samples/
│       │   ├── factura_nativa.pdf
│       │   ├── boleta_escaneada.jpg
│       │   └── imagen_ruido.png
│       └── expected/
│           └── factura_nativa.json
│
├── scripts/
│   ├── calibrate_hsv.py            # genera rangos rojos desde muestras
│   └── run_batch.ps1               # wrapper Windows
│
├── documentos_ingresados/          # input (gitignored)
├── quarantine/                     # documentos que requieren revisión
└── output/
    └── Rendicion_Gastos_OCR_*.xlsx
```

---

## 4. Roadmap por Fases

> **Regla de oro:** cada fase debe cerrar con **tests pasando + commit + tag**. No avanzar a la siguiente fase con deuda técnica abierta.

---

### **Fase 0 — Bootstrap del entorno** ⏱️ 0.5 día

**Objetivo:** tener un `python -m ocr_tributario --version` funcionando.

**Tareas:**
1. Crear estructura de carpetas según sección 3.
2. Inicializar repo git: `git init && git add . && git commit -m "chore: project skeleton"`.
3. Crear `requirements.txt` y `venv`.
4. Instalar Tesseract OCR + idioma español (ver §2.1).
5. Configurar `.gitignore` (excluir `venv/`, `documentos_ingresados/`, `output/`, `quarantine/`, `.env`).
6. Crear `src/ocr_tributario/__main__.py` mínimo con `--version`.

**Definition of Done (DoD):**
- ✅ `python -m ocr_tributario --version` imprime versión.
- ✅ `pytest --collect-only` encuentra al menos 1 test.
- ✅ `README.md` con instrucciones de setup.

---

### **Fase 1 — Configuración externa y logging** ⏱️ 0.5 día

**Objetivo:** todo parámetro ajustable vive en `config/settings.yaml`, nunca hardcodeado.

**Entregables:**
- `config/settings.yaml` con:
  ```yaml
  paths:
    input_dir: "documentos_ingresados"
    output_dir: "output"
    quarantine_dir: "quarantine"
    tesseract_cmd: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
  hsv_red:
    lower1: [0, 70, 50]
    upper1: [10, 255, 255]
    lower2: [170, 70, 50]
    upper2: [180, 255, 255]
    min_area: 5000
    aspect_ratio: [1.5, 3.5]
  ocr:
    lang: "spa"
    psm: 6
    whitelist: "0123456789Kk.-RUTN° "
  excel:
    template_columns:
      - Mes
      - Fecha
      - Nro Boleta Factura
      - PROVEEDOR
      - RUT
      - Total
      - Descripción del gasto
      - Observaciones
  ```
- `src/ocr_tributario/config/loader.py` con función `load_settings()`.
- `src/ocr_tributario/utils/logging.py` con loguru configurado (rotación diaria, nivel configurable).

**DoD:**
- ✅ Tests unitarios para `loader.py`.
- ✅ Cambiar un parámetro en YAML se refleja sin tocar código.

---

### **Fase 2 — Pipeline de ingesta y enrutamiento** ⏱️ 1 día

**Objetivo:** dado un directorio, retornar lista tipada de archivos a procesar.

**Entregables:**
- `utils/magic_bytes.py` con `detect_file_type(path) -> "pdf" | "image" | "unknown"`.
- `ingestion/scanner.py` con `scan_directory(dir) -> list[DocumentInput]`.
- `ingestion/router.py` con `route(input) -> Literal["pdf_native", "pdf_image", "image"]` según:
  1. Magic bytes.
  2. Si es PDF, ¿tiene capa de texto extraíble? (test: `pdfplumber.open(...).pages[0].extract_text()` con > 50 chars).

**DoD:**
- ✅ Test con fixture PDF nativo → `pdf_native`.
- ✅ Test con fixture PDF escaneado → `pdf_image`.
- ✅ Test con JPG/PNG → `image`.

---

### **Fase 3 — Preprocesamiento OpenCV** ⏱️ 1.5 días

**Objetivo:** `preprocess_image(path) -> np.ndarray` lista para OCR.

**Componentes:**
1. **Conversión a escala de grises.**
2. **Filtro bilateral** (preserva bordes).
3. **Umbralizado adaptativo gaussiano.**
4. **Deskew** con `cv2.minAreaRect` y `cv2.warpAffine`.
5. **Opcional:** eliminación de sombras con `cv2.morphologyEx` + dilate + medianBlur.

**Entregables:**
- `preprocessing/opencv_pipeline.py`.
- Script `scripts/calibrate_hsv.py` para ajustar rangos con muestras reales.
- Tests con imagen rotada 5°/15° → verificar ángulo enderezado.

**DoD:**
- ✅ Imagen con rotación conocida de 7° se corrige a ≤ 0.5°.
- ✅ Tiempo de procesamiento < 500 ms por imagen en CPU estándar.

---

### **Fase 4 — Segmentación HSV del recuadro SII** ⏱️ 1 día

**Objetivo:** aislar programáticamente el recuadro rojo y retornar ROI + coordenadas.

**Componentes:**
1. `cv2.cvtColor(img, cv2.COLOR_BGR2HSV)`.
2. Dos máscaras `cv2.inRange` (rojo bajo H≈0 y rojo alto H≈170–180).
3. `cv2.add` de máscaras + `cv2.dilate` con kernel 5×5.
4. `cv2.findContours` con `RETR_EXTERNAL`.
5. Filtros: `area > min_area` y `aspect_ratio ∈ [min, max]`.
6. Padding configurable alrededor del bounding box.

**Entregables:**
- `preprocessing/hsv_segmenter.py` con función `extract_sii_red_box(img_bgr) -> tuple[np.ndarray, tuple[int,int,int,int]] | None`.
- Tests con fixtures de facturas reales (5+ muestras) → recall > 90%.

**DoD:**
- ✅ Detecta recuadro en 9 de 10 facturas de muestra.
- ✅ Retorna `None` (sin crash) en facturas sin recuadro rojo.

---

### **Fase 5 — Motores de extracción** ⏱️ 2 días

**Objetivo:** tres motores especializados, uno por ruta del enrutador.

#### 5.1 `extractors/pdf_native.py` (pdfplumber)
- `extract_native_pdf_data(path) -> dict[str, str]` con claves `provider_raw`, `sii_raw`, `totals_raw`.
- Estrategia `page.crop(bbox)` con coordenadas relativas.
- Manejo multipágina: tomar primera página + concatenar texto si hay más.

#### 5.2 `extractors/image_fallback.py` (PDF → imagen → OCR)
- Renderizar PDF escaneado con `pypdfium2` a 300 DPI.
- Pasar por pipeline OpenCV + segmentador HSV + OCR.

#### 5.3 `extractors/ocr_tesseract.py` (PyTesseract)
- `ocr_red_box(cropped)`: PSM 6, whitelist restringida.
- `ocr_with_anchors(full_img)`: usar `image_to_data()` para coordenadas, buscar palabras clave `"TOTAL"`, `"NETO"`, `"RUT"`, `"FACTURA"` y extraer tokens a la derecha.

**DoD:**
- ✅ PDF nativo de muestra extrae texto idéntico al original (diff = 0).
- ✅ Imagen de muestra: OCR del recuadro rojo tiene ≥ 95% de accuracy en RUT + Folio.
- ✅ Tests con imágenes de baja calidad documentan el piso de calidad.

---

### **Fase 6 — Validadores y parsers deterministas** ⏱️ 1.5 días

**Objetivo:** convertir texto crudo en campos estructurados validados.

**Entregables:**
- `validators/rut.py`:
  - `clean_and_validate_rut(raw) -> str | None` con algoritmo Módulo 11 documentado.
  - Tests con RUTs válidos, inválidos, con K, con 0.
- `validators/regex_patterns.py`:
  - `extract_date(text) -> date | None` con normalización a `YYYY-MM-DD`.
  - `extract_total(text) -> int | None` (manejo de separadores de miles).
  - `extract_folio(text) -> int | None`.
- `validators/normalizers.py`:
  - `normalize_provider_name(raw) -> str` (trim, colapsar espacios, mayúsculas selectivas).

**DoD:**
- ✅ 100% tests pasando en `test_rut_validator.py`.
- ✅ Fechas ambiguas se validan contra rango lógico (mes 1–12, día según mes).

---

### **Fase 7 — Modelos de datos** ⏱️ 0.5 día

**Objetivo:** tipado fuerte de extremo a extremo.

**Entregables:**
- `models/invoice.py` con `@dataclass` o Pydantic:
  ```python
  class InvoiceRecord:
      archivo_origen: str
      mes: str | None
      fecha: date | None
      nro_documento: int | None
      proveedor: str | None
      rut: str | None
      total: int | None
      estado: Literal["OK", "QUARANTINE", "REJECTED"]
      motivo_revision: str | None
      timestamp_proceso: datetime
  ```

**DoD:**
- ✅ Validación Pydantic rechaza registros mal formados antes de exportar.

---

### **Fase 8 — Orquestador end-to-end** ⏱️ 2 días

**Objetivo:** `pipeline.process_directory(input_dir) -> ProcessingReport`.

**Componentes:**
- `orchestrator/pipeline.py`:
  - Loop sobre archivos.
  - Por archivo: ingesta → preprocess → segment → extract → validate → record.
  - Manejo de excepciones por documento (un fallo no rompe el batch).
  - `concurrent.futures.ProcessPoolExecutor` para paralelizar (configurable).
  - Barra de progreso con `tqdm`.
- `orchestrator/hitl.py`:
  - Si `estado == "QUARANTINE"` → mueve archivo a `quarantine/<timestamp>_<nombre>`.
  - Genera `quarantine/revisar_manual.xlsx` con los campos faltantes.

**DoD:**
- ✅ Procesar 100 documentos mixtos sin crash.
- ✅ Tasa de éxito > 95% en PDFs nativos, > 80% en imágenes de calidad media.
- ✅ Documentos fallidos quedan en `quarantine/` con metadata.

---

### **Fase 9 — Exportación a Excel** ⏱️ 0.5 día

**Objetivo:** escribir `Rendicion_Gastos_OCR_<YYYY-MM>.xlsx` con el esquema exacto de la planilla de la empresa.

**Entregables:**
- `exporters/excel_writer.py` con función `export_records(records, output_path)`.
- Usar `openpyxl` con formato:
  - Header en negrita + freeze first row.
  - Anchos de columna predefinidos.
  - Formato de fecha `YYYY-MM-DD` (no datetime).
  - Formato de total con separador de miles.
- Una hoja `Procesados` + hoja `Revisión Manual` (consolidado de quarantine).

**DoD:**
- ✅ Excel abre correctamente en Microsoft Excel y LibreOffice.
- ✅ Columnas coinciden al pegar en la planilla de rendición.

---

### **Fase 10 — Pruebas end-to-end** ⏱️ 1.5 días

**Objetivo:** validar con datos reales antes de producción.

**Plan de pruebas:**
1. Recolectar **30+ facturas/boletas reales** anonimizadas (10 nativas PDF, 10 escaneadas JPG, 10 baja calidad).
2. Anotar ground truth en `tests/fixtures/expected/`.
3. Correr pipeline completo.
4. Comparar salida vs ground truth → calcular:
   - **Tasa de extracción correcta por campo** (Fecha, Folio, RUT, Total, Proveedor).
   - **Tasa de falsos positivos** en validador RUT.
   - **Tiempo promedio por documento**.

**DoD:**
- ✅ Métricas documentadas en `docs/benchmarks.md`.
- ✅ Casos fallidos clasificados en 3 categorías: ilegible, mal formato, error de pipeline.

---

### **Fase 11 — Empaquetado y distribución** ⏱️ 1 día

**Opciones (elige según tu contexto):**

| Opción | Comando | Caso de uso |
|---|---|---|
| **CLI Python puro** | `python -m ocr_tributario --input ./docs --output ./out.xlsx` | Equipo técnico, scripts, CI |
| **Script PowerShell** | `.\scripts\run_batch.ps1` | Operador contable en Windows |
| **PyInstaller .exe** | `pyinstaller --onefile ocr_tributario.spec` | Usuario sin Python instalado |
| **Servicio programado** | Task Scheduler de Windows | Ejecución nocturna automática |

**Recomendación:** empezar con CLI + `.ps1`. PyInstaller solo si se distribuye a usuarios no técnicos.

**DoD:**
- ✅ `.exe` generado y probado en máquina limpia sin Python.
- ✅ Task Scheduler ejecuta correctamente a la hora programada.

---

### **Fase 12 — Operación y mantenimiento** ⏱️ continuo

**Runbook operativo:**

1. **Cola diaria:**
   - Operador deposita PDFs/imágenes en `documentos_ingresados/`.
   - Ejecuta `.\scripts\run_batch.ps1` (o Task Scheduler lo lanza a las 23:00).
   - Sistema escribe `output/Rendicion_Gastos_OCR_<fecha>.xlsx`.

2. **Revisión HITL:**
   - Operador abre `quarantine/revisar_manual.xlsx`.
   - Completa campos faltantes manualmente.
   - Decisión: ¿corregir ground truth del pipeline o es caso excepcional?

3. **Monitoreo:**
   - Log diario en `logs/ocr_<fecha>.log`.
   - Alerta si tasa de quarantine > 20% (correo/Teams opcional).

4. **Re-entrenamiento de umbrales:**
   - Cada 3 meses correr `scripts/calibrate_hsv.py` con nuevas muestras.
   - Actualizar `config/settings.yaml`.

5. **Versionado:**
   - Tags semánticos: `v0.1.0` (fase 5 OK), `v1.0.0` (producción), `v1.1.0` (mejoras HITL).

---

## 5. Riesgos y Plan de Mitigación

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Rango HSV descalibrado → 0% detección | Alta | Alto | Fase 4 + script calibrate + benchmark continuo |
| R2 | Facturas sin recuadro rojo (antiguas) | Media | Medio | Fallback a OCR completo + flag manual |
| R3 | Tesseract no instalado en máquina destino | Alta | Bloqueante | Installer documentado + check al inicio del pipeline |
| R4 | PDFs con texto vectorial corrupto | Baja | Medio | Fallback a OCR sobre render del PDF |
| R5 | RUT con DV `0` o `K` mal OCR | Media | Alto | Validador Módulo 11 + revisión HITL |
| R6 | Excel con encoding roto (ñ, tildes) | Media | Bajo | Forzar `utf-8-sig` y `openpyxl` con `encoding='utf-8'` |
| R7 | Memoria insuficiente con 1000+ docs | Baja | Medio | Streaming + process pool con `chunksize` |
| R8 | Cambio de formato del SII | Baja | Alto | Tests de regresión + alerta por aumento de quarantine |

---

## 6. Cómo Dejarlo Operativo (checklist final)

### 6.1 Pre-producción
- [ ] Todas las fases 0–11 completadas con DoD ✅
- [ ] Benchmark ≥ 95% en PDFs nativos guardado en `docs/benchmarks.md`
- [ ] README.md con guía rápida (3 pasos)
- [ ] `.env.example` con todas las variables
- [ ] Script `scripts/run_batch.ps1` probado en máquina limpia

### 6.2 Puesta en producción
- [ ] Crear `documentos_ingresados/` en carpeta de red compartida (si aplica)
- [ ] Crear `output/` y `quarantine/` con permisos correctos
- [ ] Configurar **Windows Task Scheduler**:
  - Trigger: diario 23:00
  - Action: `powershell.exe -ExecutionPolicy Bypass -File C:\ruta\scripts\run_batch.ps1`
  - Settings: "Run whether user is logged on or not"
- [ ] Configurar rotación de logs (loguru lo hace, validar tamaño)
- [ ] Probar 1 semana en modo "shadow" (genera output pero no se usa aún)

### 6.3 Operación estable
- [ ] Operador contable capacitado en flujo HITL
- [ ] Canal de soporte definido (correo/Slack) para fallos
- [ ] Revisión mensual de métricas + ajuste de umbrales HSV
- [ ] Backup semanal de `quarantine/` + logs

---

## 7. Estimación de Esfuerzo Total

| Fase | Días | Acumulado |
|---|---|---|
| 0 — Bootstrap | 0.5 | 0.5 |
| 1 — Config | 0.5 | 1.0 |
| 2 — Ingesta | 1.0 | 2.0 |
| 3 — OpenCV | 1.5 | 3.5 |
| 4 — HSV SII | 1.0 | 4.5 |
| 5 — Extractores | 2.0 | 6.5 |
| 6 — Validadores | 1.5 | 8.0 |
| 7 — Modelos | 0.5 | 8.5 |
| 8 — Orquestador | 2.0 | 10.5 |
| 9 — Excel | 0.5 | 11.0 |
| 10 — Tests E2E | 1.5 | 12.5 |
| 11 — Empaquetado | 1.0 | 13.5 |
| 12 — Operación | continuo | — |

**Total para v1.0 operativa: ~13.5 días hábiles (≈ 3 semanas) para un dev.**

---

## 8. Próximos Pasos Inmediatos

1. **Hoy:** crear la estructura de carpetas y subir `requirements.txt` a git.
2. **Mañana:** instalar Tesseract + verificar `tesseract --list-langs` incluye `spa`.
3. **Esta semana:** cerrar Fase 0 + Fase 1 + Fase 2.
4. **Siguiente semana:** Fase 3 + Fase 4 (aquí se ve "magia" con las primeras detecciones).
5. **Iterar:** cada fase cierra con demo al usuario/contable para feedback temprano.

---

## 9. Glosario de Referencia Rápida

| Término | Significado |
|---|---|
| **HSV** | Espacio de color (Hue, Saturation, Value) más robusto que RGB para detectar colores bajo luz variable |
| **Deskew** | Enderezar imagen rotada |
| **Módulo 11** | Algoritmo de dígito verificador usado en RUT chileno |
| **PSM** | Page Segmentation Mode de Tesseract (6 = bloque uniforme) |
| **HITL** | Human-in-the-Loop: revisión manual de casos dudosos |
| **ROI** | Region of Interest: recorte de una zona específica de la imagen |
| **Whitelist** | Set de caracteres permitidos que Tesseract debe reconocer |

---

**Documento vivo.** Actualizar este roadmap al cerrar cada fase. La versión final v1.0 debe quedar en `docs/roadmap-v1.0.md` como referencia histórica.