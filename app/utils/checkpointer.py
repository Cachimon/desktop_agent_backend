from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from typing import Optional, Any, AsyncIterator, Sequence
from datetime import datetime
from sqlalchemy import text
import json


class _LangChainEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 BaseMessage 和 set 等不可序列化类型"""

    def default(self, obj):
        if isinstance(obj, BaseMessage):
            return obj.model_dump()
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


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
        channel_values = dict(data.get("channel_values", {}))
        # 将 messages 中的 dict 还原为 BaseMessage 对象
        if "messages" in channel_values and isinstance(
            channel_values["messages"], list
        ):
            _MSG_MAP = {
                "human": HumanMessage,
                "ai": AIMessage,
                "system": SystemMessage,
                "tool": ToolMessage,
            }
            msgs = []
            for m in channel_values["messages"]:
                if isinstance(m, dict) and m.get("type") in _MSG_MAP:
                    cls = _MSG_MAP[m["type"]]
                    kwargs = {k: v for k, v in m.items() if k != "type"}
                    msgs.append(cls(**kwargs))
                else:
                    msgs.append(m)
            channel_values["messages"] = msgs
        updated_channels = data.get("updated_channels")
        if isinstance(updated_channels, list):
            updated_channels = set(updated_channels)
        return Checkpoint(
            v=data.get("v", 1),
            id=data.get("id", ""),
            ts=data.get("ts", ""),
            channel_values=channel_values,
            channel_versions=data.get("channel_versions", {}),
            versions_seen=data.get("versions_seen", {}),
            updated_channels=updated_channels,
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
            # set 不可 JSON 序列化，转为 list
            result["updated_channels"] = list(checkpoint["updated_channels"])
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

    @staticmethod
    def _deserialize_value(value: Any) -> Any:
        """反序列化单个值，将 dict 还原为 BaseMessage 对象"""
        _MSG_MAP = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
            "tool": ToolMessage,
        }
        if isinstance(value, dict) and value.get("type") in _MSG_MAP:
            cls = _MSG_MAP[value["type"]]
            kwargs = {k: v for k, v in value.items() if k != "type"}
            return cls(**kwargs)
        return value

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """保存 pending writes，LangGraph 在 interrupt 时需要调用此方法"""
        thread_id = self._get_thread_id(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")
        if not thread_id:
            return

        async with self.engine.connect() as conn:
            # 同一 checkpoint + task 的 writes 需要整体替换（重试时 writes 数量可能不同）
            await conn.execute(
                text("""
                    DELETE FROM checkpoint_writes
                    WHERE thread_id = :thread_id
                    AND checkpoint_id = :checkpoint_id
                    AND task_id = :task_id
                """),
                {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                },
            )
            if writes:
                await conn.execute(
                    text("""
                        INSERT INTO checkpoint_writes (thread_id, checkpoint_id, task_id, channel, value)
                        VALUES (:thread_id, :checkpoint_id, :task_id, :channel, :value)
                    """),
                    [
                        {
                            "thread_id": thread_id,
                            "checkpoint_id": checkpoint_id,
                            "task_id": task_id,
                            "channel": channel,
                            "value": json.dumps(value, cls=_LangChainEncoder),
                        }
                        for channel, value in writes
                    ],
                )
            await conn.commit()

    async def aget(
        self,
        config: RunnableConfig | None,
    ) -> Optional[Checkpoint]:
        """获取最新的检查点"""
        thread_id = self._get_thread_id(config)
        if not thread_id:
            return None

        async with self.engine.connect() as conn:
            # 子查询先找 checkpoint_id，避免 ORDER BY 时加载大 JSON 列导致 sort memory 溢出
            result = await conn.execute(
                text("""
                    SELECT checkpoint 
                    FROM checkpoints 
                    WHERE checkpoint_id = (
                        SELECT checkpoint_id
                        FROM checkpoints
                        WHERE thread_id = :thread_id 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    )
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

        try:
            checkpoint_json = json.dumps(checkpoint_data, cls=_LangChainEncoder)
            metadata_json = json.dumps(metadata_data, cls=_LangChainEncoder)
        except TypeError as e:
            print(f"[Checkpointer] json.dumps 序列化失败: {e}")
            print(f"[Checkpointer] checkpoint_data 类型: {type(checkpoint_data)}")
            # 打印 channel_values 中每个值的类型，定位问题字段
            cv = checkpoint_data.get("channel_values", {})
            for k, v in cv.items():
                print(f"  channel_values[{k!r}] type={type(v).__name__}")
                if isinstance(v, list) and v:
                    print(f"    [0] type={type(v[0]).__name__}")
            raise

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
                    "checkpoint": checkpoint_json,
                    "metadata": metadata_json,
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
            # 子查询先找 checkpoint_id，避免 ORDER BY 时加载大 JSON 列导致 sort memory 溢出
            result = await conn.execute(
                text("""
                    SELECT checkpoint, metadata 
                    FROM checkpoints 
                    WHERE checkpoint_id = (
                        SELECT checkpoint_id
                        FROM checkpoints
                        WHERE thread_id = :thread_id 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    )
                """),
                {"thread_id": thread_id},
            )

            row = result.fetchone()
            if row:
                checkpoint = self._deserialize_checkpoint(json.loads(row[0]))
                metadata = self._deserialize_metadata(
                    json.loads(row[1]) if row[1] else {}
                )

                # 加载 pending writes
                checkpoint_id = checkpoint.get("id", "")
                writes_result = await conn.execute(
                    text("""
                        SELECT task_id, channel, value
                        FROM checkpoint_writes
                        WHERE thread_id = :thread_id
                        AND checkpoint_id = :checkpoint_id
                    """),
                    {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
                )
                pending_writes = []
                for wrow in writes_result.fetchall():
                    w_task_id, w_channel, w_value_json = wrow
                    w_value = self._deserialize_value(json.loads(w_value_json))
                    pending_writes.append((w_task_id, w_channel, w_value))

                return CheckpointTuple(
                    config=config or {},
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=None,
                    pending_writes=pending_writes or None,
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
            # 子查询先找 checkpoint_id 列表，避免 ORDER BY 时加载大 JSON 列导致 sort memory 溢出
            id_query = """
                SELECT checkpoint_id
                FROM checkpoints
                WHERE thread_id = :thread_id
            """
            params = {"thread_id": thread_id}

            if before:
                before_thread_id = self._get_thread_id(before)
                if before_thread_id:
                    id_query += " AND created_at < (SELECT created_at FROM checkpoints WHERE thread_id = :before_thread_id ORDER BY created_at DESC LIMIT 1)"
                    params["before_thread_id"] = before_thread_id

            id_query += " ORDER BY created_at DESC"

            if limit:
                id_query += f" LIMIT {limit}"

            id_result = await conn.execute(text(id_query), params)
            id_rows = id_result.fetchall()
            if not id_rows:
                return

            ids = [r[0] for r in id_rows]
            placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
            data_params = {f"id_{i}": cid for i, cid in enumerate(ids)}

            result = await conn.execute(
                text(f"""
                    SELECT checkpoint_id, checkpoint, metadata 
                    FROM checkpoints 
                    WHERE checkpoint_id IN ({placeholders})
                """),
                data_params,
            )
            # 按 ids 顺序组织结果
            row_map = {}
            for row in result.fetchall():
                row_map[row[0]] = (row[1], row[2])

            for cid in ids:
                if cid not in row_map:
                    continue
                cp_json, meta_json = row_map[cid]
                checkpoint = self._deserialize_checkpoint(json.loads(cp_json))
                metadata = self._deserialize_metadata(
                    json.loads(meta_json) if meta_json else {}
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
            await conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    thread_id VARCHAR(255) NOT NULL,
                    checkpoint_id VARCHAR(255) NOT NULL,
                    task_id VARCHAR(255) NOT NULL,
                    channel VARCHAR(255) NOT NULL,
                    value JSON NOT NULL,
                    INDEX idx_thread_checkpoint (thread_id, checkpoint_id)
                )
            """)
            )
            await conn.commit()
