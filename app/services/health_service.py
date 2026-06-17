from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import engine
from app.schemas.health import ComponentStatus, HealthResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)


class HealthService:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def check_health(self) -> HealthResponse:
        components: dict[str, ComponentStatus] = {}
        overall_healthy = True

        mysql_status = await self._check_mysql()
        components["mysql"] = mysql_status
        if mysql_status.status != "healthy":
            overall_healthy = False

        langgraph_status = ComponentStatus(status="healthy")
        components["langgraph"] = langgraph_status

        taskiq_status = ComponentStatus(status="not_configured")
        components["taskiq"] = taskiq_status

        return HealthResponse(
            status="healthy" if overall_healthy else "unhealthy",
            components=components,
        )

    async def _check_mysql(self) -> ComponentStatus:
        try:
            import time
            from sqlalchemy import text
            from app.models.base import async_session_maker

            start = time.time()
            async with async_session_maker() as session:
                await session.execute(text("SELECT 1"))
            latency = int((time.time() - start) * 1000)
            return ComponentStatus(status="healthy", latency_ms=latency)
        except Exception as e:
            logger.error("mysql_health_check_failed", error=str(e))
            return ComponentStatus(status="unhealthy", error=str(e))
