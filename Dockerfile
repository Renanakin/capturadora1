FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CAPTURADOR_INPUT_DIR=/app/documentos_ingresados \
    CAPTURADOR_OUTPUT_DIR=/app/output \
    CAPTURADOR_QUARANTINE_DIR=/app/quarantine \
    TESSERACT_CMD=tesseract \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create necessary directories
RUN mkdir -p $CAPTURADOR_INPUT_DIR $CAPTURADOR_OUTPUT_DIR $CAPTURADOR_QUARANTINE_DIR /app/uploads

# Expose API port
EXPOSE 8000

# Default command to run the API
CMD ["python", "-m", "ocr_tributario", "api", "--host", "0.0.0.0", "--port", "8000"]
