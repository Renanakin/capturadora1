"""Motor de Plantillas con Auto-Aprendizaje (HITL)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from ocr_tributario.validators.regex_patterns import _parse_money, extract_date

TEMPLATES_PATH = Path("src/ocr_tributario/config/templates.yaml")


class TemplateEngine:
    def __init__(self):
        self.templates = self._load_templates()

    def _load_templates(self) -> list[dict[str, Any]]:
        if not TEMPLATES_PATH.exists():
            return []
        with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("proveedores", []) if data else []

    def _save_templates(self) -> None:
        TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
            yaml.dump({"proveedores": self.templates}, f, allow_unicode=True, sort_keys=False)

    def match_and_extract(self, ocr_text: str) -> dict[str, Any] | None:
        """Busca si el texto pertenece a una plantilla y extrae los datos."""
        if not ocr_text:
            return None
            
        text_lower = ocr_text.lower()
        
        for template in self.templates:
            # Check if keywords match
            keywords = template.get("keywords_identificacion", [])
            if any(kw.lower() in text_lower for kw in keywords):
                logger.info(f"Plantilla '{template['nombre']}' detectada.")
                
                extracted = {
                    "proveedor": template["nombre"],
                    "rut": template.get("rut_defecto"),
                }
                
                # Apply rules
                rules = template.get("reglas", {})
                
                # Regla Total
                if "total" in rules and rules["total"].startswith("regex:"):
                    pat = rules["total"].replace("regex: ", "").replace("regex:", "").strip()
                    m = re.search(pat, ocr_text, re.IGNORECASE)
                    if m:
                        val = _parse_money(m.group(1))
                        if val:
                            extracted["total"] = val
                
                # Regla Fecha
                if "fecha" in rules and rules["fecha"].startswith("regex:"):
                    pat = rules["fecha"].replace("regex: ", "").replace("regex:", "").strip()
                    m = re.search(pat, ocr_text, re.IGNORECASE)
                    if m:
                        d = extract_date(m.group(1))
                        if d:
                            extracted["fecha_emision"] = d
                            
                return extracted
                
        return None

    def learn_template(self, proveedor: str, ocr_text: str, total_real: int | str | None, fecha_real: str | None, rut: str | None = None) -> bool:
        """Aprende una nueva regla basándose en las correcciones manuales."""
        logger.info(f"Auto-Aprendizaje iniciado para proveedor: {proveedor}")
        
        # Buscar o crear plantilla
        template = next((t for t in self.templates if t["nombre"].lower() == proveedor.lower()), None)
        if not template:
            template = {
                "nombre": proveedor,
                "keywords_identificacion": [proveedor],
                "rut_defecto": rut or "EXTRANJERO",
                "reglas": {}
            }
            self.templates.append(template)
            
        # Aprender Total
        if total_real:
            val_str = str(total_real)
            # Buscar la linea exacta donde aparece el total en el OCR
            for line in ocr_text.splitlines():
                # Normalizar la linea quitando espacios dobles y signos raros
                line_norm = re.sub(r'\s+', ' ', line).strip()
                val_formateado = f"{val_str[:2]}.{val_str[2:]}" if len(val_str) > 3 else val_str
                
                # Buscamos si el valor está en la linea (ej "10000" o "10.000")
                if val_str in line_norm or val_formateado in line_norm:
                    # Encontramos la línea, tomamos todo lo que está antes del valor como prefijo
                    parts = re.split(fr'({val_str}|{val_formateado})', line_norm)
                    if len(parts) > 1 and parts[0].strip():
                        prefix = parts[0].strip()
                        # Escapar regex
                        prefix_escapado = re.escape(prefix)
                        # Reemplazar signos pesos por opcionales
                        prefix_escapado = prefix_escapado.replace(r'\$', r'\$?')
                        
                        rule = f"regex: {prefix_escapado}\\s*([\\d\\.]+)"
                        template["reglas"]["total"] = rule
                        logger.info(f"Regla de total aprendida: {rule}")
                        break

        # Guardar cambios
        self._save_templates()
        return True
