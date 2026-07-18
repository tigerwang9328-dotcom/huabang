from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ai_assistant_routes_reject_anonymous_requests():
    endpoints = [
        ("GET", "/api/v1/ai-assistant/brief", None),
        ("GET", "/api/v1/ai-assistant/conversations", None),
        ("POST", "/api/v1/ai-assistant/conversations", {}),
    ]

    for method, path, payload in endpoints:
        response = client.request(method, path, json=payload)
        assert response.status_code == 401, (method, path, response.text)


def test_ai_assistant_router_is_registered_without_replacing_legacy_ai_route():
    route_paths = {route.path for route in app.routes}

    assert "/api/v1/ai/ask" in route_paths
    assert "/api/v1/ai-assistant/brief" in route_paths
    assert "/api/v1/ai-assistant/conversations" in route_paths
    assert "/api/v1/ai-assistant/conversations/{conversation_id}/messages" in route_paths
