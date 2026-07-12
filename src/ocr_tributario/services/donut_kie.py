"""Servicio de rescate AI usando Donut (Document Understanding Transformer).

Se activa solo cuando el OCR tradicional falla. Extrae JSON directamente
de la imagen usando un modelo Visual Transformer entrenado en recibos.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger
from PIL import Image

# Cargamos de forma lazy para no penalizar el inicio rápido de la CLI si no se usa
_PROCESSOR = None
_MODEL = None


def _init_donut():
    global _PROCESSOR, _MODEL
    if _PROCESSOR is not None and _MODEL is not None:
        return

    logger.info("Inicializando modelo Donut (naver-clova-ix/donut-base-finetuned-cord-v2) en CPU...")
    try:
        from transformers import DonutProcessor, VisionEncoderDecoderModel
        _PROCESSOR = DonutProcessor.from_pretrained("naver-clova-ix/donut-base-finetuned-cord-v2")
        _MODEL = VisionEncoderDecoderModel.from_pretrained("naver-clova-ix/donut-base-finetuned-cord-v2")
        logger.info("Modelo Donut cargado exitosamente.")
    except ImportError:
        logger.error("No se encontraron las librerías 'torch' o 'transformers'.")
        raise
    except Exception as e:
        logger.error(f"Error cargando Donut: {e}")
        raise


def extract_with_donut(image_path: Path) -> dict[str, Any]:
    """Extrae datos de la imagen usando el transformer visual Donut."""
    _init_donut()

    logger.info(f"Donut procesando imagen: {image_path.name}")
    try:
        image = Image.open(image_path).convert("RGB")
        pixel_values = _PROCESSOR(image, return_tensors="pt").pixel_values

        task_prompt = "<s_cord-v2>"
        decoder_input_ids = _PROCESSOR.tokenizer(task_prompt, add_special_tokens=False, return_tensors="pt").input_ids

        outputs = _MODEL.generate(
            pixel_values,
            decoder_input_ids=decoder_input_ids,
            max_length=_MODEL.decoder.config.max_position_embeddings,
            pad_token_id=_PROCESSOR.tokenizer.pad_token_id,
            eos_token_id=_PROCESSOR.tokenizer.eos_token_id,
            use_cache=True,
            bad_words_ids=[[_PROCESSOR.tokenizer.unk_token_id]],
            return_dict_in_generate=True,
        )

        sequence = _PROCESSOR.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(_PROCESSOR.tokenizer.eos_token, "").replace(_PROCESSOR.tokenizer.pad_token, "")
        sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()
        
        extracted_data = _PROCESSOR.token2json(sequence)
        logger.debug(f"Donut output crudo: {extracted_data}")
        return extracted_data
    except Exception as e:
        logger.error(f"Fallo en procesamiento de Donut para {image_path.name}: {e}")
        return {}
