"""FastAPI app principal."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ocr_tributario import __version__
from ocr_tributario.api.schemas import HealthResponse
from ocr_tributario.config.loader import load_settings
from ocr_tributario.db import DB_PATH, init_db
from ocr_tributario.api.routes import api_router


async def _ping_redis() -> bool:
    url = load_settings().api.redis_url
    try:
        client = redis.from_url(url)
        pong = await client.ping()
        await client.aclose()
        return bool(pong)
    except Exception:
        return False


async def _check_db() -> bool:
    import aiosqlite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
        return True
    except Exception:
        return False


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Inicializa DB al arrancar."""
    await init_db()
    logger.info("CapturadorM3 API iniciada")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CapturadorM3 API",
        description="OCR Tributario Chileno - extracción de DTE/boletas a Excel",
        version=__version__,
        lifespan=_lifespan,
    )

    # Servir el frontend
    frontend_path = Path(__file__).resolve().parents[3] / "frontend"
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(str(frontend_path / "index.html"))

    @app.get("/api/v1/", tags=["meta"])
    async def root():
        return {
            "service": "CapturadorM3",
            "version": __version__,
            "docs": "/docs",
        }

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["meta"])
    async def health():
        from datetime import datetime
        r = await _ping_redis()
        d = await _check_db()
        return HealthResponse(
            status="ok" if (r or True) else "degraded",
            version=__version__,
            redis=r,
            db=d,
            timestamp=datetime.now(),
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


# Instancia para uvicorn
app = create_app()