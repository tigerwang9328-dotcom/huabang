"""Regression tests for authentication on business and ERP routes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/store/list", None),
        ("GET", "/api/v1/product/list", None),
        ("GET", "/api/v1/product/sku-list", None),
        ("POST", "/api/v1/sync/baison/products", {}),
        ("POST", "/api/v1/sync/baison/skus", {}),
        ("GET", "/api/v1/inventory/warehouses", None),
        ("GET", "/api/v1/inventory/balance", None),
        ("POST", "/api/v1/sync/baison/warehouses", {}),
        ("POST", "/api/v1/sync/baison/inventory", {}),
        ("POST", "/api/v1/integrations/baison/test/shop-list", {}),
        ("POST", "/api/v1/integrations/baison/sync/shop-list", {}),
        ("POST", "/api/v1/integrations/baison/sync/shops", {}),
        ("GET", "/api/v1/integrations/baison/shops", None),
        ("GET", "/api/v1/integrations/baison/shops/TEST", None),
    ],
)
def test_business_route_rejects_anonymous_requests(method, path, payload):
    response = client.request(method, path, json=payload)

    assert response.status_code == 401, (method, path, response.text)

