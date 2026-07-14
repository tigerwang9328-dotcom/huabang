import json

import httpx
import pytest

import app.integrations.baison.client as client_module
from app.integrations.baison.client import BaisonClient
from app.integrations.baison.config import BaisonConfig
from app.integrations.baison.exceptions import BaisonRequestError


def _config() -> BaisonConfig:
    return BaisonConfig(
        base_url="https://baison.example.test/api",
        app_key="test-key",
        app_secret="unit-test-placeholder",
        sign_method="md5",
        api_version="2.0",
        format="json",
        page_size=100,
        http_method="POST",
    )


class _Response:
    status_code = 200
    text = json.dumps({"code": 0, "data": {"rows": []}})

    def json(self):
        return json.loads(self.text)


class _FlakyClient:
    calls = 0
    fail_until = 0

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, data):
        type(self).calls += 1
        if type(self).calls <= type(self).fail_until:
            raise httpx.RemoteProtocolError(
                "peer closed connection",
                request=httpx.Request("POST", url),
            )
        return _Response()

    def get(self, url, params):
        return self.post(url, params)


def test_transport_errors_retry_with_bounded_backoff(monkeypatch):
    _FlakyClient.calls = 0
    _FlakyClient.fail_until = 2
    sleeps = []
    monkeypatch.setattr(client_module.httpx, "Client", _FlakyClient)
    monkeypatch.setattr("time.sleep", sleeps.append)

    response = BaisonClient(_config()).request("stock.goods_sscx", {"page": 1})

    assert response.status_code == 200
    assert _FlakyClient.calls == 3
    assert sleeps == [1.0, 2.0]


def test_transport_error_stops_after_three_attempts(monkeypatch):
    _FlakyClient.calls = 0
    _FlakyClient.fail_until = 10
    sleeps = []
    monkeypatch.setattr(client_module.httpx, "Client", _FlakyClient)
    monkeypatch.setattr("time.sleep", sleeps.append)

    with pytest.raises(BaisonRequestError, match="RemoteProtocolError"):
        BaisonClient(_config()).request("stock.goods_sscx", {"page": 1})

    assert _FlakyClient.calls == 3
    assert sleeps == [1.0, 2.0]


def test_successful_request_is_not_retried(monkeypatch):
    _FlakyClient.calls = 0
    _FlakyClient.fail_until = 0
    sleeps = []
    monkeypatch.setattr(client_module.httpx, "Client", _FlakyClient)
    monkeypatch.setattr("time.sleep", sleeps.append)

    response = BaisonClient(_config()).request("pos.qtlsd.list_get", {"page": 1})

    assert response.status_code == 200
    assert _FlakyClient.calls == 1
    assert sleeps == []
