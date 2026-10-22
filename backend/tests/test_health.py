from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["app"] == "DashPilot API"
    assert body["llm_provider"] in ("gemini", "claude")
    assert "llm_configured" in body and body["llm_model"]


def test_cors_allows_frontend_origin():
    res = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_system_info_ok():
    res = client.get("/api/system/info")
    assert res.status_code == 200
    body = res.json()
    assert body["app"] == "DashPilot API"
    assert "python_version" in body
    assert "platform" in body
    assert "storage_dir" in body
    assert "powerbi_desktop_installed" in body

