from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.data.import_job_router import router as import_job_router
from app.modules.data.router import router as data_router
from app.modules.data.takeover_router import router as takeover_router
from app.modules.digital_twin.dependency_router import router as dependency_router
from app.modules.digital_twin.process_map_router import router as process_map_router
from app.modules.digital_twin.router import router as digital_twin_router
from app.modules.evaluasi.router import router as evaluasi_router
from app.modules.simulasi.router import router as simulasi_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(data_router)
api_router.include_router(takeover_router)
api_router.include_router(import_job_router)
api_router.include_router(digital_twin_router)
api_router.include_router(dependency_router)
api_router.include_router(process_map_router)
api_router.include_router(simulasi_router)
api_router.include_router(evaluasi_router)
