

from app.models.base import engine
from app.utils.checkpointer import MySQLCheckpointSaver


# async def get_checkpointer() -> AsyncMySQLSaver:
#     checkpointer = AsyncMySQLSaver(engine)
#     await checkpointer.setup()
#     return checkpointer

async def get_checkpointer() -> MySQLCheckpointSaver:
    checkpointer = MySQLCheckpointSaver(engine)
    await checkpointer.setup()
    return checkpointer