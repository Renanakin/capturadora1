import re
from ocr_tributario.models.cedula import CedulaRecord
from ocr_tributario.services.ocr_paddle import OCRResult
from ocr_tributario.validators.rut import clean_rut, validate_rut

def parse_cedula_fields(ocr_result: OCRResult, archivo_origen: str, engine_used: str) -> CedulaRecord:
    text = ocr_result.full_text.upper()
    
    rut_encontrado = None
    numero_doc = None
    fecha_nac = None
    
    # Buscar RUT
    rut_regex = re.compile(r'\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b|\b\d{7,8}-[\dkK]\b')
    ruts = [clean_rut(m.group(0)) for m in rut_regex.finditer(text)]
    valid_ruts = [r for r in ruts if validate_rut(r)]
    if valid_ruts:
        rut_encontrado = valid_ruts[0]
        
    # Buscar numero documento (ej: 123.456.789 o 123456789 cerca de "DOCUMENTO")
    m_doc = re.search(r'NUMERO\s*DE\s*DOCUMENTO\s*[\n:]*\s*([\d\.]+)', text)
    if m_doc:
        numero_doc = m_doc.group(1).replace('.', '')
        
    # Buscar fecha nacimiento (DD/MM/YYYY o DD MMM YYYY)
    m_nac = re.search(r'FECHA\s*DE\s*NACIMIENTO\s*[\n:]*\s*(\d{2}[\s/.-]+\w+[\s/.-]+\d{4})', text)
    if m_nac:
        fecha_nac = m_nac.group(1)
        
    estado = "QUARANTINE"
    if rut_encontrado and numero_doc:
        estado = "OK"
        
    return CedulaRecord(
        archivo_origen=archivo_origen,
        rut=rut_encontrado,
        numero_documento=numero_doc,
        fecha_nacimiento=fecha_nac,
        estado=estado,
        ocr_engine=engine_used,
        ocr_avg_score=ocr_result.avg_score
    )
