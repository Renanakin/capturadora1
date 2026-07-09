from fastapi import APIRouter
from . import ocr, jobs, utils

api_router = APIRouter()
api_router.include_router(ocr.router, prefix="/ocr", tags=["ocr"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["async"])
api_router.include_router(utils.router, prefix="/validate", tags=["utils"])
