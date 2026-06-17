from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.config import get_settings
from app.utils.exceptions import AppException
from app.utils.trace import generate_trace_id, set_trace_id
from app.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    setup_logging(settings.app.LOG_LEVEL)
    logger.info("application_starting", host=settings.app.HOST, port=settings.app.PORT)
    yield
    from app.models.base import engine
    await engine.dispose()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="AI Desktop Agent Backend",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def trace_id_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

    @application.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning("app_exception", error_code=exc.error_code, status_code=exc.status_code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @application.exception_handler(PydanticValidationError)
    async def validation_exception_handler(request: Request, exc: PydanticValidationError):
        from app.utils.trace import get_trace_id
        logger.warning("validation_error", errors=exc.errors())
        return JSONResponse(
            status_code=400,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Parameter validation failed",
                "detail": {"errors": exc.errors()},
                "trace_id": get_trace_id(),
            },
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        from app.utils.trace import get_trace_id
        logger.error("unhandled_exception", exc_type=type(exc).__name__, exc_message=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": {},
                "trace_id": get_trace_id(),
            },
        )

    api_prefix = settings.app.API_V1_PREFIX

    from app.routers import auth as auth_router
    from app.routers import chat as chat_router
    from app.routers import conversations as conversations_router
    from app.routers import health as health_router
    from app.routers import reserved as reserved_router
    from app.routers import settings as settings_router
    from app.routers import skills as skills_router
    from app.routers import tools as tools_router

    application.include_router(auth_router.router, prefix=api_prefix)
    application.include_router(chat_router.router, prefix=api_prefix)
    application.include_router(conversations_router.router, prefix=api_prefix)
    application.include_router(skills_router.router, prefix=api_prefix)
    application.include_router(settings_router.router, prefix=api_prefix)
    application.include_router(health_router.router, prefix=api_prefix)
    application.include_router(tools_router.router, prefix=api_prefix)
    application.include_router(reserved_router.router, prefix=api_prefix)

    return application


app = create_app()
