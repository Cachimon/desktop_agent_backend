from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/", response_model=HealthResponse)
async def health_check():
    svc = HealthService()
    result = await svc.check_health()
    if result.status == "unhealthy":
        return JSONResponse(status_code=503, content=result.model_dump())
    return result
