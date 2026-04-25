"""Tests for request ID middleware"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.request_id import RequestIDMiddleware, get_request_id, request_id_var


def test_middleware_adds_request_id():
    """Middleware should add X-Request-ID to response"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    
    @app.get("/test")
    def test_route():
        return {"message": "test"}
    
    client = TestClient(app)
    response = client.get("/test")
    
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_middleware_preserves_provided_request_id():
    """Should use client-provided request ID if present"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    
    @app.get("/test")
    def test_route():
        return {"message": "test"}
    
    client = TestClient(app)
    custom_id = "custom-request-id-12345"
    response = client.get("/test", headers={"X-Request-ID": custom_id})
    
    assert response.headers["X-Request-ID"] == custom_id


def test_get_request_id_in_handler():
    """Request ID should be accessible in route handlers"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    
    captured_id = None
    
    @app.get("/test")
    def test_route():
        nonlocal captured_id
        captured_id = get_request_id()
        return {"request_id": captured_id}
    
    client = TestClient(app)
    response = client.get("/test")
    
    assert captured_id is not None
    assert captured_id == response.headers["X-Request-ID"]
    assert response.json()["request_id"] == captured_id


def test_request_id_in_request_state():
    """Request ID should be in request.state"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    
    from fastapi import Request
    
    @app.get("/test")
    def test_route(request: Request):
        return {"request_id": request.state.request_id}
    
    client = TestClient(app)
    response = client.get("/test")
    
    request_id_from_response = response.json()["request_id"]
    request_id_from_header = response.headers["X-Request-ID"]
    
    assert request_id_from_response == request_id_from_header


def test_different_requests_get_different_ids():
    """Each request should get a unique ID"""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    
    @app.get("/test")
    def test_route():
        return {"message": "test"}
    
    client = TestClient(app)
    response1 = client.get("/test")
    response2 = client.get("/test")
    
    id1 = response1.headers["X-Request-ID"]
    id2 = response2.headers["X-Request-ID"]
    
    assert id1 != id2


def test_get_request_id_without_context():
    """get_request_id should return empty string outside request context"""
    # Clear any existing context
    request_id_var.set("")
    result = get_request_id()
    assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
