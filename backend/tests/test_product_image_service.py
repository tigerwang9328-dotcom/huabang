from datetime import datetime, timezone

import pytest

from app.integrations.baison.services.product_image_service import (
    _upsert_image_rows,
    fetch_product_images,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeClient:
    def __init__(self):
        self.params = None

    def request(self, method, params, timeout):
        self.params = params
        return FakeResponse({
            "code": "1", "flag": "success",
            "data": {"data": [{
                "GoodsCode": "P001", "ColorCode": "-50",
                "ImageUrl": "http://example.test/p001-50.jpg", "IsMainPic": 1,
            }]},
        })


def test_fetch_product_images_adds_baison_color_prefix():
    client = FakeClient()
    rows = fetch_product_images([("P001", "50")], client=client)
    assert client.params["Goods"] == [{"GoodsCode": "P001", "ColorCode": "-50"}]
    assert rows[0]["ImageUrl"].endswith("p001-50.jpg")


class FakeDb:
    def __init__(self):
        self.params = []

    async def execute(self, statement, params=None):
        self.params.append(params)


@pytest.mark.asyncio
async def test_upsert_matches_prefixed_api_color_to_normalized_pair():
    db = FakeDb()
    urls = await _upsert_image_rows(
        db,
        [("P001", "50")],
        [{"GoodsCode": "P001", "ColorCode": "-50", "ImageUrl": "http://example.test/p001-50.jpg", "IsMainPic": 1}],
        datetime.now(timezone.utc),
    )
    assert urls[("P001", "50")].endswith("p001-50.jpg")
    assert db.params[0]["color_code"] == "50"
