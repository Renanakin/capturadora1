from fastapi.testclient import TestClient
from ocr_tributario import __version__
from ocr_tributario.api.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/api/v1/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "CapturadorM3"
    assert body["version"] == __version__
    assert body["docs"] == "/docs"

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
