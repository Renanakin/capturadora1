from fastapi import APIRouter
from ocr_tributario.api.schemas import RutValidationRequest, RutValidationResponse
from ocr_tributario.validators.rut import validate_rut, clean_rut, _modulo11_dv

router = APIRouter()

@router.post(
    "/rut",
    response_model=RutValidationResponse,
    summary="Valida un RUT (Módulo 11) y devuelve el formato canónico",
)
async def validate_rut_endpoint(req: RutValidationRequest):
    canonico = validate_rut(req.rut)
    cleaned = clean_rut(req.rut)
    dv_calc = None
    if cleaned and len(cleaned) >= 2:
        try:
            dv_calc = _modulo11_dv(cleaned[:-1])
        except Exception:
            dv_calc = None
    return RutValidationResponse(
        rut_input=req.rut,
        canonico=canonico,
        valido=canonico is not None,
        dv_calculado=dv_calc,
    )
