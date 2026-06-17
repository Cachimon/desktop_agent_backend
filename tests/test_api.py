import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_reserved_endpoints(client: AsyncClient):
    response = await client.get("/api/v1/mcp/servers")
    assert response.status_code == 501
    data = response.json()
    assert data["error_code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_send_code_missing_csrf(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/send-code",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error_code"] == "CSRF_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_login_missing_csrf(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "code": "123456"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_conversations_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_skills_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/skills")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_error_format(client: AsyncClient):
    response = await client.get("/api/v1/search/semantic")
    assert response.status_code == 501
    data = response.json()
    assert "error_code" in data
    assert "message" in data
    assert "trace_id" in data
