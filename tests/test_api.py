from fastapi.testclient import TestClient
from ocr_tributario.api.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/api/v1/")
    assert response.status_code == 200
    assert response.json() == {"service": "CapturadorM3", "version": "1.0.0", "docs": "/docs"}

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
