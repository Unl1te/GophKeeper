from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RequestLoggingMiddleware


def _make_app():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_middleware_logs_method_path_status():
    with patch("app.middleware.logger") as mock_logger:
        client = TestClient(_make_app())
        response = client.get("/ping")

    assert response.status_code == 200
    assert mock_logger.info.called
    args = mock_logger.info.call_args[0]
    # logger.info(fmt, method, path, status, duration_ms)
    assert args[1] == "GET"
    assert args[2] == "/ping"
    assert args[3] == 200


def test_middleware_passes_response_through():
    client = TestClient(_make_app())
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
