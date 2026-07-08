# Stack OCR en Python para cédula chilena y DTE con validación de RUT y ejemplo FastAPI

Este documento propone un stack completo para procesar cédula chilena y documentos tributarios electrónicos (DTE) en Python, con validación de RUT, clasificación documental y una base de API en FastAPI. La recomendación principal es usar PaddleOCR como motor OCR base, complementado con OpenCV para preprocesado, validadores de negocio para Chile y, en algunos casos, Tesseract como fallback o segunda opinión.[cite:19][cite:21][cite:25]

## Arquitectura recomendada

El stack más estable para un sistema chileno de OCR documental se puede dividir en seis capas. PaddleOCR ofrece un pipeline OCR general y capacidades de conversión estructurada de documentos, mientras Tesseract sigue siendo una opción útil para escenarios de OCR clásico y como respaldo operativo.[cite:19][cite:21][cite:34]

1. Ingesta: imágenes JPG/PNG, PDF escaneado, PDF generado por impresora virtual y capturas de celular.[cite:19][cite:21]
2. Preprocesado: rotación, deskew, recorte, binarización, mejora de contraste y reducción de ruido antes del OCR.[cite:25][cite:28]
3. OCR: PaddleOCR como motor principal; Tesseract con `spa` como fallback o segunda pasada en campos críticos.[cite:21][cite:25][cite:31]
4. Clasificación documental: reglas y heurísticas para distinguir cédula, boleta, factura, guía, nota de crédito u otros DTE.[cite:26][cite:32]
5. Parsing y validación: extracción de RUT emisor/receptor, folio, fecha, totales, razón social, tipo de documento y validación del dígito verificador.[cite:26][cite:32]
6. Exposición API: FastAPI para recibir archivos, orquestar pipeline, responder JSON y dejar trazabilidad para ERP, e-commerce o integraciones SII internas.[cite:25][cite:34]

## Componentes del stack

| Capa | Herramienta | Función principal |
|---|---|---|
| OCR principal | PaddleOCR | Detección y reconocimiento de texto en imágenes y PDF, con pipeline OCR y salida estructurable.[cite:19][cite:21] |
| OCR fallback | Tesseract + pytesseract | Segunda lectura en español, útil para campos concretos o contingencia.[cite:25][cite:31][cite:34] |
| Preprocesado | OpenCV + Pillow | Deskew, threshold, crop, resize, limpieza de ruido y normalización visual.[cite:25][cite:28] |
| API | FastAPI | Endpoints para subir documentos, procesar y devolver JSON.[cite:25][cite:34] |
| Modelado | Pydantic | Esquemas tipados para respuesta y validación de entrada; componente natural del stack FastAPI. |
| PDF | pdf2image / pypdf | Rasterización de PDFs escaneados o lectura previa de metadatos. |
| Código de barras 2D | lector PDF417 o zxing/zbar | Validación complementaria para representaciones impresas de DTE con timbre/PDF417.[cite:32] |
| Persistencia | PostgreSQL / Supabase | Guardado de JSON OCR, auditoría, colas de reproceso y estados del documento. |
| Cola | Celery / RQ / Dramatiq | Procesamiento asíncrono para lotes o PDFs de múltiples páginas. |

## Qué reconoce cada flujo

### Cédula chilena

La cédula requiere una extracción orientada por zonas, porque el OCR general por sí solo puede confundir nombre, RUN, nacionalidad, fechas o número de documento cuando la foto viene inclinada, con reflejos o con fondos complejos. Los documentos de identidad chilenos también presentan desafíos de procesamiento específicos que obligan a usar preprocesado y validación posterior más estricta.[cite:16]

Campos sugeridos:

- RUN/RUT.
- Nombres y apellidos.
- Fecha de nacimiento.
- Fecha de vencimiento.
- Número de documento.
- Nacionalidad.
- Sexo, si el formato de la cédula procesada lo expone claramente.
- MRZ o líneas inferiores, si la imagen tiene suficiente calidad.

Flujo sugerido:

1. Detectar contorno del documento y corregir perspectiva.
2. Normalizar iluminación y contraste.
3. Ejecutar OCR general sobre toda la cara frontal.
4. Ejecutar OCR por regiones en campos candidatos, por ejemplo RUN y número de documento.
5. Normalizar texto, corregir separadores y validar RUN con módulo 11.
6. Aplicar reglas de consistencia, por ejemplo que la fecha de vencimiento sea posterior a la de nacimiento.

### DTE y boletas chilenas

El SII define que los documentos tributarios electrónicos se generan en XML según el formato oficial, y además la representación impresa incorpora simbología PDF417 con información del timbre electrónico. En el caso de boletas electrónicas, el formato técnico oficial contempla campos como RUT receptor y otros datos del documento, por lo que el parser debe apoyarse tanto en OCR como en reglas estructurales del documento impreso.[cite:32][cite:26]

Campos sugeridos para DTE impreso o PDF rasterizado:

- Tipo de documento, por ejemplo factura, boleta, nota de crédito o guía.
- Folio.
- RUT emisor.
- Razón social emisor.
- Giro o actividad, si aparece impreso.
- Fecha de emisión.
- RUT receptor, cuando aplique.[cite:26]
- Monto neto, IVA, exento, total.
- Ítems o resumen de ítems.
- Timbre o presencia de PDF417, si se puede leer por visión o por lector específico.[cite:32]

Heurísticas mínimas de clasificación:

- Si aparecen palabras como “FACTURA ELECTRÓNICA”, “NOTA DE CRÉDITO ELECTRÓNICA” o “GUÍA DE DESPACHO”, clasificar por tipo explícito.[cite:32]
- Si aparece “BOLETA ELECTRÓNICA” y el layout corresponde al formato de boleta del SII, tratar como boleta.[cite:26][cite:29]
- Si existe “RUT:” en cabecera más “Folio”, casi siempre se trata de DTE o boleta tributaria chilena.[cite:26][cite:32]
- La presencia de código PDF417 o timbre electrónico aumenta la confianza documental para DTE impresos.[cite:32]

## Validación de RUT

La validación del RUT debe ejecutarse siempre después del OCR y antes de aceptar un documento como confiable. El OCR suele introducir errores comunes como reemplazar `0` por `O`, `1` por `I`, quitar guiones o separar mal miles, por lo que primero se normaliza y luego se valida el dígito verificador por módulo 11.

Reglas prácticas:

- Aceptar entrada con puntos y guion, pero normalizar a `XXXXXXXX-DV`.
- Convertir `k` a `K`.
- Rechazar longitud imposible o caracteres no válidos.
- Marcar como baja confianza si el OCR entregó símbolos ambiguos cerca del DV.

Implementación Python:

```python
def clean_rut(value: str) -> str:
    value = value.upper().replace('.', '').replace(' ', '')
    if '-' not in value and len(value) > 1:
        value = f"{value[:-1]}-{value[-1]}"
    return value


def validate_rut(rut: str) -> bool:
    rut = clean_rut(rut)
    if '-' not in rut:
        return False
    body, dv = rut.split('-')
    if not body.isdigit() or dv not in '0123456789K':
        return False

    reverse_digits = map(int, reversed(body))
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for i, d in enumerate(reverse_digits):
        total += d * factors[i % len(factors)]

    mod = 11 - (total % 11)
    expected = '0' if mod == 11 else 'K' if mod == 10 else str(mod)
    return dv == expected
```

## Estructura de proyecto sugerida

```text
app/
├── main.py
├── api/
│   └── routes_ocr.py
├── core/
│   ├── settings.py
│   └── logging.py
├── services/
│   ├── preprocess.py
│   ├── ocr_paddle.py
│   ├── ocr_tesseract.py
│   ├── classify.py
│   ├── parse_cedula.py
│   ├── parse_dte.py
│   └── validators.py
├── schemas/
│   └── ocr.py
└── utils/
    └── text.py
```

Esta separación permite desacoplar OCR, clasificación y parsing de negocio, lo que simplifica pruebas, tuning por tipo documental y escalado a colas asíncronas. También ayuda a dejar un fallback por campo sin acoplar toda la aplicación al mismo motor OCR.

## Dependencias sugeridas

```bash
pip install fastapi uvicorn python-multipart pydantic
pip install paddleocr paddlepaddle
pip install pytesseract pillow opencv-python numpy
pip install pdf2image pypdf
```

Notas operativas:

- PaddleOCR puede instalarse como librería Python y exponer pipeline OCR y PP-Structure para documentos.[cite:21][cite:27]
- Tesseract requiere instalación del motor en el sistema y el modelo `spa` dentro de `tessdata`; luego `pytesseract` actúa como wrapper Python.[cite:25][cite:31][cite:34]
- Para Tesseract, la calidad mejora cuando las imágenes se aproximan a 300 DPI y cuando se ajusta el modo de segmentación de página según el layout.[cite:28]

## Ejemplo de pipeline por etapas

### 1. Preprocesado

El preprocesado debería ser configurable por tipo documental. Una cédula necesita corrección de perspectiva y brillo; una boleta térmica suele necesitar binarización agresiva; una factura PDF escaneada puede requerir deskew y aumento de nitidez.[cite:25][cite:28]

```python
import cv2
import numpy as np


def preprocess_image(file_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15
    )
    return thr
```

### 2. OCR con PaddleOCR

PaddleOCR publica un pipeline OCR general para reconocimiento de texto y además capacidades de extracción más estructurada sobre documentos complejos. Para una primera versión, conviene usarlo como motor principal y devolver texto más cajas o regiones, no solo texto plano.[cite:19][cite:21]

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='es')


def run_paddle_ocr(image_path: str):
    result = ocr.ocr(image_path, cls=True)
    lines = []
    for page in result:
        for item in page:
            box, (text, score) = item
            lines.append({
                "text": text,
                "score": float(score),
                "box": box,
            })
    return lines
```

### 3. Fallback con Tesseract

Tesseract puede funcionar como segunda pasada para campos de baja confianza o documentos con tipografía simple. Debe instalarse con soporte `spa`, y `pytesseract` permite leer texto o datos con coordenadas desde Python.[cite:25][cite:31][cite:34]

```python
import pytesseract
from PIL import Image


def run_tesseract(image_path: str) -> str:
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang='spa')
```

### 4. Clasificación simple

```python
import re


def classify_document(text: str) -> str:
    t = text.upper()
    if 'CEDULA' in t or 'IDENTIDAD' in t or 'APELLIDOS' in t:
        return 'cedula'
    if 'FACTURA ELECTRONICA' in t:
        return 'factura_electronica'
    if 'BOLETA ELECTRONICA' in t:
        return 'boleta_electronica'
    if 'NOTA DE CREDITO' in t:
        return 'nota_credito'
    if re.search(r'\bFOLIO\b', t) and re.search(r'\bRUT\b', t):
        return 'dte_generico'
    return 'desconocido'
```

### 5. Extracción de RUT

```python
import re

RUT_REGEX = re.compile(r'\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b|\b\d{7,8}-[\dkK]\b')


def extract_ruts(text: str) -> list[str]:
    return list({clean_rut(m.group(0)) for m in RUT_REGEX.finditer(text)})
```

## Ejemplo FastAPI completo

Este ejemplo expone un endpoint único para subir un archivo, ejecutar preprocesado, OCR, clasificación y validaciones básicas. En producción conviene separar el procesamiento pesado en worker asíncrono, pero esta base sirve bien para una versión inicial o una API interna.

```python
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import tempfile
import os
import re
from paddleocr import PaddleOCR
import pytesseract
from PIL import Image

app = FastAPI(title="OCR Chile API")
ocr = PaddleOCR(use_angle_cls=True, lang='es')
RUT_REGEX = re.compile(r'\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b|\b\d{7,8}-[\dkK]\b')


class OCRLine(BaseModel):
    text: str
    score: float


class OCRResponse(BaseModel):
    document_type: str
    ruts_found: List[str]
    valid_ruts: List[str]
    extracted_text: str
    lines: List[OCRLine]
    folio: Optional[str] = None
    total: Optional[str] = None


def clean_rut(value: str) -> str:
    value = value.upper().replace('.', '').replace(' ', '')
    if '-' not in value and len(value) > 1:
        value = f"{value[:-1]}-{value[-1]}"
    return value



def validate_rut(rut: str) -> bool:
    rut = clean_rut(rut)
    if '-' not in rut:
        return False
    body, dv = rut.split('-')
    if not body.isdigit() or dv not in '0123456789K':
        return False
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for i, d in enumerate(map(int, reversed(body))):
        total += d * factors[i % len(factors)]
    mod = 11 - (total % 11)
    expected = '0' if mod == 11 else 'K' if mod == 10 else str(mod)
    return dv == expected



def classify_document(text: str) -> str:
    t = text.upper()
    if 'CEDULA' in t or 'IDENTIDAD' in t or 'APELLIDOS' in t:
        return 'cedula'
    if 'FACTURA ELECTRONICA' in t:
        return 'factura_electronica'
    if 'BOLETA ELECTRONICA' in t:
        return 'boleta_electronica'
    if 'NOTA DE CREDITO' in t:
        return 'nota_credito'
    if 'FOLIO' in t and 'RUT' in t:
        return 'dte_generico'
    return 'desconocido'



def extract_ruts(text: str) -> list[str]:
    return list({clean_rut(m.group(0)) for m in RUT_REGEX.finditer(text)})



def parse_basic_fields(text: str) -> tuple[Optional[str], Optional[str]]:
    folio = None
    total = None

    m_folio = re.search(r'FOLIO\s*:?\s*(\d+)', text, re.IGNORECASE)
    if m_folio:
        folio = m_folio.group(1)

    m_total = re.search(r'TOTAL\s*:?\s*\$?\s*([\d\.,]+)', text, re.IGNORECASE)
    if m_total:
        total = m_total.group(1)

    return folio, total



def run_paddle(path: str):
    result = ocr.ocr(path, cls=True)
    lines = []
    texts = []
    for page in result:
        for item in page:
            _, (text, score) = item
            texts.append(text)
            lines.append(OCRLine(text=text, score=float(score)))
    return lines, '\n'.join(texts)


@app.post('/ocr', response_model=OCRResponse)
async def process_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='Archivo inválido')

    suffix = os.path.splitext(file.filename)[1] or '.jpg'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        lines, full_text = run_paddle(tmp_path)
        doc_type = classify_document(full_text)
        ruts = extract_ruts(full_text)
        valid_ruts = [r for r in ruts if validate_rut(r)]
        folio, total = parse_basic_fields(full_text)

        return OCRResponse(
            document_type=doc_type,
            ruts_found=ruts,
            valid_ruts=valid_ruts,
            extracted_text=full_text,
            lines=lines,
            folio=folio,
            total=total,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
```

## Mejoras recomendadas para producción

### Para cédula

- Detectar y recortar automáticamente el documento antes del OCR.
- Procesar anverso y reverso por separado.
- Incorporar OCR por regiones para RUN, nombre y número de documento.
- Añadir scoring por campo, no solo scoring global.
- Usar validaciones cruzadas entre fecha de nacimiento, vencimiento y edad aparente del documento.

### Para DTE

- Soportar PDFs multipágina y lotes.
- Agregar lectura explícita de PDF417 cuando el timbre sea visible.[cite:32]
- Crear parsers separados por tipo: factura, boleta, nota de crédito y guía.
- Mapear resultados al esquema interno de tu ERP o sistema tributario.
- Si el origen es XML DTE real, priorizar parser XML sobre OCR y dejar OCR solo para representación impresa.[cite:32]

### Para calidad y observabilidad

- Guardar imagen original, imagen preprocesada y JSON final.
- Registrar confianza promedio por línea y por campo.
- Marcar documentos con baja confianza para revisión humana.
- Añadir pruebas con set real chileno: boletas térmicas, facturas impresas, capturas móviles y cédulas con diferentes condiciones de luz.

## Estrategia operativa recomendada

La estrategia más práctica para Chile es usar dos rutas distintas. Para cédula, conviene un pipeline muy guiado por regiones y validación estricta; para DTE, conviene un pipeline híbrido que primero intente parser estructural cuando exista XML y solo recurra a OCR cuando el insumo sea imagen o PDF escaneado.[cite:21][cite:32]

Diseño sugerido:

- `route /ocr/cedula`: pipeline específico con campos esperados y validadores fuertes.
- `route /ocr/dte`: clasificador de tipo DTE, parser tributario y lectura de RUT/folio/montos.
- `route /ocr/general`: fallback para documentos no clasificados.
- `route /validate/rut`: utilidad simple para otros sistemas internos.

## Recomendación final de stack

La combinación más sólida para una primera versión productiva es la siguiente:

- PaddleOCR como motor principal.[cite:19][cite:21]
- Tesseract `spa` como fallback y segunda opinión en campos ambiguos.[cite:25][cite:31][cite:34]
- OpenCV para preprocesado intensivo.[cite:25][cite:28]
- FastAPI para exponer servicios internos y batch API.[cite:25][cite:34]
- Parsers separados para cédula y DTE.
- Validador RUT obligatorio en toda extracción chilena.
- Cola asíncrona para PDFs grandes y procesos masivos.
- Persistencia JSON + auditoría para revisión manual.

Con este stack se obtiene una base realista para integrarlo con ERP, e-commerce, automatizaciones en Python o agentes que necesiten leer documentación chilena con control de calidad y validación de negocio.
