from app.api.v1.finance_v2 import router


def test_v2_routes_are_separate_from_legacy_write_paths_during_read_only_gate():
    routes = {(route.path, next(iter(route.methods))) for route in router.routes}

    assert ("/finance-center/v2/books", "GET") in routes
    assert ("/finance-center/v2/vouchers", "POST") in routes
    assert ("/finance-center/v2/vouchers/{voucher_id}/commands", "POST") in routes
    assert ("/finance-center/v2/history/vouchers", "GET") in routes
