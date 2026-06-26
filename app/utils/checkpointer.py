from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langchain_core.runnables import RunnableConfig
from typing import Optional, Any, AsyncIterator
from datetime import datetime
from sqlalchemy import text
import json


class MySQLCheckpointSaver(BaseCheckpointSaver):
    """自定义 MySQL Checkpointer"""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    @staticmethod
    def _get_thread_id(config: RunnableConfig | None) -> str | None:
        """从 config 中提取 thread_id"""
        if config is None:
            return None
        return config.get("configurable", {}).get("thread_id")

    @staticmethod
    def _deserialize_checkpoint(data: dict) -> Checkpoint:
        """反序列化 Checkpoint"""
        return Checkpoint(
            v=data.get("v", 1),
            id=data.get("id", ""),
            ts=data.get("ts", ""),
            channel_values=data.get("channel_values", {}),
            channel_versions=data.get("channel_versions", {}),
            versions_seen=data.get("versions_seen", {}),
            updated_channels=data.get("updated_channels"),
        )

    @staticmethod
    def _serialize_checkpoint(checkpoint: Checkpoint) -> dict:
        """序列化 Checkpoint"""
        result = {
            "v": checkpoint["v"],
            "id": checkpoint["id"],
            "ts": checkpoint["ts"],
            "channel_values": checkpoint["channel_values"],
            "channel_versions": checkpoint["channel_versions"],
            "versions_seen": checkpoint["versions_seen"],
        }
        if checkpoint.get("updated_channels") is not None:
            result["updated_channels"] = checkpoint["updated_channels"]
        return result

    @staticmethod
    def _deserialize_metadata(data: dict) -> CheckpointMetadata:
        """反序列化 CheckpointMetadata"""
        return CheckpointMetadata(
            source=data.get("source"),
            step=data.get("step"),
            parents=data.get("parents", {}),
        )

    @staticmethod
    def _serialize_metadata(metadata: CheckpointMetadata) -> dict:
        """序列化 CheckpointMetadata"""
        result = {}
        if metadata.get("source") is not None:
            result["source"] = metadata["source"]
        if metadata.get("step") is not None:
            result["step"] = metadata["step"]
        if metadata.get("parents"):
            result["parents"] = metadata["parents"]
        if metadata.get("run_id") is not None:
            result["run_id"] = metadata["run_id"]
        return result

    async def aget(
        self,
        config: RunnableConfig | None,
    ) -> Optional[Checkpoint]:
        """获取最新的检查点"""
        thread_id = self._get_thread_id(config)
        if not thread_id:
            return None

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT checkpoint 
                    FROM checkpoints 
                    WHERE thread_id = :thread_id 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """),
                {"thread_id": thread_id},
            )
            row = result.fetchone()
            if row:
                return self._deserialize_checkpoint(json.loads(row[0]))
            return None

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """保存检查点，返回更新后的 config"""
        thread_id = self._get_thread_id(config)
        if not thread_id:
            raise ValueError("thread_id is required")

        checkpoint_data = self._serialize_checkpoint(checkpoint)
        metadata_data = self._serialize_metadata(metadata)
        checkpoint_id = checkpoint["id"]

        async with self.engine.connect() as conn:
            await conn.execute(
                text("""
                    INSERT INTO checkpoints (
                        checkpoint_id, 
                        thread_id, 
                        checkpoint, 
                        metadata, 
                        created_at
                    )
                    VALUES (:checkpoint_id, :thread_id, :checkpoint, :metadata, :created_at)
                    ON DUPLICATE KEY UPDATE
                        checkpoint = :checkpoint,
                        metadata = :metadata,
                        created_at = :created_at
                """),
                {
                    "checkpoint_id": checkpoint_id,
                    "thread_id": thread_id,
                    "checkpoint": json.dumps(checkpoint_data),
                    "metadata": json.dumps(metadata_data),
                    "created_at": datetime.utcnow(),
                },
            )
            await conn.commit()

        return {
            **config,
            "configurable": {
                **config.get("configurable", {}),
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            },
        }

    async def aget_tuple(
        self,
        config: RunnableConfig | None,
    ) -> Optional[CheckpointTuple]:
        """获取检查点元组"""
        thread_id = self._get_thread_id(config)
        if not thread_id:
            return None

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT checkpoint, metadata 
                    FROM checkpoints 
                    WHERE thread_id = :thread_id 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """),
                {"thread_id": thread_id},
            )

            row = result.fetchone()
            if row:
                checkpoint = self._deserialize_checkpoint(json.loads(row[0]))
                metadata = self._deserialize_metadata(
                    json.loads(row[1]) if row[1] else {}
                )

                return CheckpointTuple(
                    config=config or {},
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=None,
                )

            return None

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """列出所有检查点"""
        thread_id = self._get_thread_id(config)
        if not thread_id:
            return

        async with self.engine.connect() as conn:
            query = """
                SELECT checkpoint, metadata 
                FROM checkpoints 
                WHERE thread_id = :thread_id
            """
            params = {"thread_id": thread_id}

            if before:
                before_thread_id = self._get_thread_id(before)
                if before_thread_id:
                    query += " AND created_at < (SELECT created_at FROM checkpoints WHERE thread_id = :before_thread_id ORDER BY created_at DESC LIMIT 1)"
                    params["before_thread_id"] = before_thread_id

            query += " ORDER BY created_at DESC"

            if limit:
                query += f" LIMIT {limit}"

            result = await conn.execute(text(query), params)
            rows = result.fetchall()

            for row in rows:
                checkpoint = self._deserialize_checkpoint(json.loads(row[0]))
                metadata = self._deserialize_metadata(
                    json.loads(row[1]) if row[1] else {}
                )

                yield CheckpointTuple(
                    config=config or {},
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=None,
                )

    async def setup(self) -> None:
        """创建表"""
        async with self.engine.connect() as conn:
            await conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    checkpoint_id VARCHAR(255) NOT NULL UNIQUE,
                    thread_id VARCHAR(255) NOT NULL,
                    checkpoint JSON NOT NULL,
                    metadata JSON,
                    created_at DATETIME NOT NULL,
                    INDEX idx_thread_id (thread_id),
                    INDEX idx_checkpoint_id (checkpoint_id)
                )
            """)
            )
            await conn.commit()
