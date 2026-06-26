# AI Desktop Agent Backend

AI Desktop Agent 后端服务 — 基于 FastAPI + LangGraph 的智能体后端骨架。

## 快速开始

### 前置条件

- Python 3.10+
- MySQL 8.0+
- Redis 7 (可选，Taskiq 预留)


### 1. 启动 MySQL

```bash
docker-compose up -d mysql
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 3. 生成 RS256 密钥对

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```
(If no openssl, use Git Bash or install from https://slproweb.com/products/Win32OpenSSL.html)

### 4. 安装依赖

```bash
pip install -r requirements.txt
```
或
```bash
uv sync
```

### 5. 运行数据库迁移

```bash
alembic upgrade head
```

### 6. 启动服务

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 7. 访问 API 文档

浏览器打开 http://127.0.0.1:8000/docs

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/send-code | 发送验证码 |
| POST | /api/v1/auth/login | 验证码登录 |
| POST | /api/v1/auth/refresh | 刷新令牌 |
| POST | /api/v1/auth/logout | 登出 |
| GET | /api/v1/auth/me | 当前用户 |
| POST | /api/v1/chat/stream | SSE 流式对话 |
| POST | /api/v1/hitl/confirm | HITL 确认 |
| POST | /api/v1/conversations | 创建会话 |
| GET | /api/v1/conversations | 会话列表 |
| GET | /api/v1/conversations/{id} | 会话详情 |
| DELETE | /api/v1/conversations/{id} | 删除会话 |
| GET | /api/v1/skills | 技能列表 |
| GET | /api/v1/skills/{name} | 技能详情 |
| GET | /api/v1/health | 健康检查 |

## 项目结构

```
app/
├── main.py          # FastAPI 入口
├── config.py        # pydantic-settings 配置
├── routers/         # API 路由层
├── services/        # 业务逻辑层
├── agents/          # LangGraph Agent 层
├── tools/           # 工具/技能层
├── repositories/    # 数据访问层
├── models/          # SQLAlchemy ORM
├── schemas/         # Pydantic Schema
├── security/        # 安全模块
├── middleware/      # 中间件
└── utils/           # 工具函数
```
## alembic相关操作

```code
alembic revision --autogenerate -m "描述" 自动生成迁移脚本
alembic upgrade head  执行最新迁移
alembic current 查看当前数据库迁移脚本
alembic stamp <revision_id> 将数据库标记为指定版本（不执行迁移）
alembic history 查看迁移历史
```