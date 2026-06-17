from langgraph.checkpoint.mysql import AsyncMySQLSaver

from app.models.base import engine


async def get_checkpointer() -> AsyncMySQLSaver:
    checkpointer = AsyncMySQLSaver(engine)
    await checkpointer.setup()
    return checkpointer
