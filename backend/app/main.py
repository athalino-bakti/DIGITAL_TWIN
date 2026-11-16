from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.session import engine
from app.modules.data.task_router import router as task_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
# Ditambahkan terakhir supaya membungkus CORS: header keamanan juga ada di respons preflight.
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(api_router)
# D-05 tasks (DIG-161) dipasang di sini, bukan di app/api/router.py, supaya tidak bentrok
# dengan PR #25 yang sedang menambah router di berkas itu. Bisa dipindah setelah #25 merge.
app.include_router(task_router, prefix="/api/v1")
