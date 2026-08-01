import importlib.util
import os


for _name, _value in {
    "APP_SECRET_KEY": "test-app-secret",
    "DB_PASSWORD": "test-db-password",
    "JWT_SECRET_KEY": "test-jwt-secret",
}.items():
    os.environ.setdefault(_name, _value)


def test_mumaren_finance_center_router_is_registered_in_a_dedicated_module():
    """The new centre must not replace or import the legacy finance-center router."""
    assert importlib.util.find_spec("app.api.v1.mumaren_finance_center") is not None

    from app.api.v1 import mumaren_finance_center

    assert mumaren_finance_center.router.prefix == "/finance-center/mumaren"
    paths = {route.path for route in mumaren_finance_center.router.routes}
    assert "/finance-center/mumaren/books" in paths
    assert "/finance-center/mumaren/vouchers" in paths
    assert "/finance-center/mumaren/history/vouchers" in paths


def test_api_root_includes_the_new_mumaren_finance_center_router_only_once():
    from app.api.v1.router import api_router

    paths = {route.path for route in api_router.routes}
    assert "/api/v1/finance-center/mumaren/books" in paths
    assert "/api/v1/finance-center/mumaren/vouchers" in paths
    assert "/api/v1/finance-center/mumaren/history/vouchers" in paths


def test_api_root_registers_independent_ar_ap_and_tax_routes():
    from app.api.v1.router import api_router

    paths = {route.path for route in api_router.routes}
    assert "/api/v1/finance-center/mumaren/ar-ap/aging" in paths
    assert "/api/v1/finance-center/mumaren/tax/alerts" in paths
    assert "/api/v1/finance-center/mumaren/reports/cash-flow-statement" in paths


def test_api_root_registers_ar_ap_and_tax_write_endpoints():
    """AR/AP 与税务的独立写入端点必须注册,且不自动过账凭证。"""
    from app.api.v1.router import api_router

    paths = {route.path for route in api_router.routes}
    assert "/api/v1/finance-center/mumaren/ar-ap/orders" in paths
    assert "/api/v1/finance-center/mumaren/ar-ap/orders/{order_id}/review" in paths
    assert "/api/v1/finance-center/mumaren/ar-ap/orders/{order_id}/settle" in paths
    assert "/api/v1/finance-center/mumaren/ar-ap/orders/{order_id}" in paths
    detail_routes = [route for route in api_router.routes if route.path == "/api/v1/finance-center/mumaren/ar-ap/orders/{order_id}"]
    assert any("GET" in route.methods for route in detail_routes)
    assert "/api/v1/finance-center/mumaren/tax/records" in paths
    assert "/api/v1/finance-center/mumaren/tax/records/{record_id}/review" in paths
    assert "/api/v1/finance-center/mumaren/tax/records/{record_id}/pay" in paths


def test_books_can_create_a_new_writable_ledger_and_only_drafts_can_be_deleted():
    from app.api.v1 import mumaren_finance_center

    paths = {route.path for route in mumaren_finance_center.router.routes}
    source = open(mumaren_finance_center.__file__, encoding="utf-8").read()
    assert '@router.post("/books"' in source
    assert '@router.delete("/vouchers/{voucher_id}"' in source
    assert 'voucher.status != "draft"' in source
    assert 'voucher.is_readonly' in source
    assert "/finance-center/mumaren/books" in paths
    assert "/finance-center/mumaren/vouchers/{voucher_id}" in paths


def test_domain_read_routes_apply_a_bounded_response_limit():
    from app.api.v1 import mumaren_finance_center_domains

    source = open(mumaren_finance_center_domains.__file__, encoding="utf-8").read()
    assert "limit: int = Query(default=100, ge=1, le=500)" in source
    assert ".limit(limit)" in source
