from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_version_falls_back_to_unknown(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"sha": "unknown"}


def test_version_reports_git_sha_override(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("GIT_SHA", "local-override-sha")
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"sha": "local-override-sha"}


def test_version_prefers_railway_sha_over_override(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railway-deployed-sha")
    monkeypatch.setenv("GIT_SHA", "local-override-sha")
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"sha": "railway-deployed-sha"}
