# CapturadorM3 - OCR Tributario Chileno

CapturadorM3 es un sistema de extracción de información (OCR) y orquestación de datos diseñado para operar sobre documentos tributarios chilenos (boletas, facturas, comprobantes) y cédulas de identidad. Su funcionamiento se basa en la privacidad, la latencia cero, y el procesamiento determinista local usando **PaddleOCR y Tesseract** sin depender de LLMs ni APIs de terceros.

---

## 🏆 Reglas de Oro para Producción (Estricto)

Este proyecto se desarrolla bajo el estándar de **0 Errores de Producción**. Cualquier contribución debe adherirse a estas reglas inquebrantables:

### 1. Seguridad y Gestión de Credenciales
- **Cero Hardcoding:** No debe existir ni una sola URL de base de datos, API Key o secreto de JWT escrito directamente en el código. Absolutamente todo va por `.env`.
- **Aislamiento de Entornos:** Las variables de desarrollo y producción deben ser distintas (e.g. `config/loader.py` para DEV y PROD). Si dependes de tu memoria para cambiar un valor antes de un deploy, el sistema ya está roto.

### 2. Arquitectura y Estructura
- **La Regla de los 30 Segundos:** Debes ser capaz de saber exactamente en qué carpeta va una nueva funcionalidad (ruta, modelo o servicio) en menos de medio minuto. La estructura semántica lo es todo.
- **Separación de Responsabilidades:** Un endpoint o ruta (`api/routes`) solo debe recibir la solicitud y delegar la acción. No debe validar lógica de negocio y consultar la base de datos en la misma función (delegar siempre en `services/`).
- **Auto-documentación:** El nombre de las carpetas y archivos debe explicar el "porqué" de la arquitectura.

### 3. Estabilidad y Pruebas
- **Red de Seguridad (Tests):** Las partes críticas (extracción OCR, endpoints, clasificación) deben contar con tests automatizados (`tests/`). No necesitamos 100% de coverage, pero sí una red que evite desastres.
- **Confianza en el Cambio:** Nadie "cruza los dedos" al subir un cambio. La seguridad para hacer deploy viene de los tests automatizados que se corren previamente.

### 4. Observabilidad y Monitoreo
- **Logging Profesional:** Prohibido usar `print()` para debuguear en producción o local. Usar el sistema de logs centralizado (actualmente `loguru`) que notifique fallos de manera estructurada.

### 5. Despliegue (Deployment)
- **Portabilidad con Docker:** Cualquier integrante del equipo debe poder lanzar el backend localmente usando Docker. El sistema tiene la responsabilidad de ser aislado para operar en cualquier entorno.

---

## 📊 Tabla de Diagnóstico (Evaluación Continua)

| Errores | Estado del Proyecto |
|---------|---------------------|
| **0 - 2** | **Listo para producción. (Nivel Objetivo - Excelencia)** |
| 3 - 5 | Frágil. Sobrevivirá, pero dará problemas a medianoche tarde o temprano. |
| 6 - 8 | Expuesto. Funciona localmente, pero en producción es un riesgo inminente. |
| 9 - 10| Oportunidad de mejora. Necesita reestructuración total desde cero. |

---

## Modos de Ejecución

1. **CLI (Procesamiento por Lotes)**
```bash
python -m ocr_tributario cli --input documentos_ingresados --verbose
```

2. **API (FastAPI Server)**
```bash
python -m ocr_tributario api --port 8000
```
La API expone los servicios de extracción a través de Swagger UI (`/docs`).

## Contribuir
Por favor, asegúrate de haber leído las Reglas de Oro. Tu PR será rechazada si hay hardcoding de IPs o si hay lógica de parseo dentro de los decoradores HTTP.