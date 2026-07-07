import warnings
import aiomysql

from app.config import get_settings
from app.models.base import engine
from app.utils.checkpointer import MySQLCheckpointSaver
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver  # 导入异步版本

# async def get_checkpointer() -> AsyncMySQLSaver:
#     checkpointer = AsyncMySQLSaver(engine)
#     await checkpointer.setup()
#     return checkpointer

# async def get_checkpointer() -> MySQLCheckpointSaver:
#     checkpointer = MySQLCheckpointSaver(engine)
#     await checkpointer.setup()
#     return checkpointer


_checkpointer: AIOMySQLSaver = None


async def get_checkpointer1() -> AIOMySQLSaver:
    global _checkpointer
    if _checkpointer:
        return _checkpointer
    settings = get_settings()
    db_user = settings.db.USER
    password = settings.db.PASSWORD
    host = settings.db.HOST
    port = settings.db.PORT
    database = settings.db.DATABASE
    db_uri = f"mysql://{db_user}:{password}@{host}:{port}/{database}"
    # 直接创建，不使用 async with
    checkpointer = AIOMySQLSaver.from_conn_string(db_uri)
    # 异步初始化连接（内部会建立连接）
    await checkpointer.setup()  # 注意 await

    _checkpointer = checkpointer
    return _checkpointer


async def get_checkpointer() -> AIOMySQLSaver:
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    settings = get_settings()

    # 1. 创建异步连接池（连接池不会被上下文管理器关闭）
    pool = await aiomysql.create_pool(
        host=settings.db.HOST,
        port=settings.db.PORT,
        user=settings.db.USER,
        password=settings.db.PASSWORD,
        db=settings.db.DATABASE,
        minsize=1,
        maxsize=10,
        autocommit=True,  # 务必开启，否则可能锁表
        charset="utf8mb4",  # 指定字符集
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci",
    )

    # 2. 直接将连接池传入 Saver 的构造函数
    # 注意：这里直接实例化，不需要调用 from_conn_string
    checkpointer = AIOMySQLSaver(pool)

    # 3. 修复表字符集排序规则
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT TABLE_NAME 
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE 'checkpoint%%'
            """,
                (settings.db.DATABASE,),
            )
            tables = await cur.fetchall()
            for (table_name,) in tables:
                await cur.execute(
                    f"ALTER TABLE {table_name} CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            await conn.commit()

    # 4. 初始化数据库表（异步方法，需要 await）
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*already exists.*")
        await checkpointer.setup()

    _checkpointer = checkpointer
    return _checkpointer
