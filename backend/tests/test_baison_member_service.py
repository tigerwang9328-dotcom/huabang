from datetime import date

import pytest

from app.integrations.baison.services.member_service import (
    BaisonMemberService,
    deduplicate_members,
    normalize_member,
    sync_members,
)


def test_normalize_member_maps_baison_legacy_fields():
    raw = {
        "DM": "VIP001",
        "GKDM": "C001",
        "MC": "测试会员",
        "customer_name": "顾客姓名",
        "SJ": "13812345678",
        "SEX": "女",
        "SR": "1990-02-03T00:00:00",
        "KLDM": "GOLD",
        "CKDM": "285204",
        "JDRQ": "2025-01-02T08:10:00",
        "XFJE": 1234.56,
        "XFCS": 7,
        "CZ_DQJE": 2800.50,
        "ZJRQ": "2026-07-09T10:11:12",
        "ZJSD": "185805",
        "STATUS": "1",
    }

    member = normalize_member(raw)

    assert member == {
        "member_no": "VIP001",
        "member_name": "顾客姓名",
        "phone": "13812345678",
        "gender": "女",
        "birthday": date(1990, 2, 3),
        "register_date": date(2025, 1, 2),
        "register_store": "285204",
        "member_level": "GOLD",
        "total_amount": 1234.56,
        "total_count": 7,
        "current_balance": 2800.50,
        "last_consume_date": date(2026, 7, 9),
        "last_consume_store": "185805",
        "status": "active",
        "raw_json": raw,
    }


def test_normalize_member_rejects_missing_member_number():
    with pytest.raises(ValueError, match="member number"):
        normalize_member({"SJ": "13812345678"})


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self.data = data


class FakeClient:
    def __init__(self):
        self.pages = []

    def request(self, method, params):
        self.pages.append((method, params.copy()))
        page = params["pageNum"]
        if page == 1:
            return FakeResponse({"code": "1", "flag": "SUCCESS", "data": {"vip": [{"DM": "A"}, {"DM": "B"}], "count": 3}})
        return FakeResponse({"code": "1", "flag": "SUCCESS", "data": {"vip": [{"DM": "C"}], "count": 3}})


def test_fetch_all_members_pages_until_reported_count():
    client = FakeClient()
    service = BaisonMemberService(client=client, page_size=2)

    members = service.fetch_all_members()

    assert [item["member_no"] for item in members] == ["A", "B", "C"]
    assert [params["pageNum"] for _, params in client.pages] == [1, 2]
    assert all(method == "crm.vip.get_list" for method, _ in client.pages)


def test_deduplicate_members_keeps_most_recent_record():
    older = normalize_member({"DM": "A", "XFJE": 10, "ZJRQ": "2026-07-01", "XGRQ": "2026-07-02"})
    newer = normalize_member({"DM": "A", "XFJE": 20, "ZJRQ": "2026-07-03", "XGRQ": "2026-07-04"})
    other = normalize_member({"DM": "B", "XFJE": 30})

    result = deduplicate_members([older, newer, other])

    assert [item["member_no"] for item in result] == ["A", "B"]
    assert result[0]["total_amount"] == 20


class FakeDb:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))

    async def flush(self):
        pass


@pytest.mark.asyncio
async def test_sync_writes_ods_then_dimension_then_removes_old_snapshot():
    db = FakeDb()
    members = [normalize_member({"DM": code}) for code in ["A", "B", "C"]]

    result = await sync_members(db, members=members)

    assert result["ok"] is True
    assert result["member_count"] == 3
    assert result["batch_no"].startswith("BAISON_MEMBER_")
    sql = "\n".join(statement for statement, _ in db.calls)
    assert "INSERT INTO ods.ods_baison_member" in sql
    assert "INSERT INTO dim.dim_member" in sql
    assert "DELETE FROM ods.ods_baison_member" in sql
    assert db.calls[0][1][0]["member_no"] == "A"


class FailingClient:
    def request(self, method, params):
        raise RuntimeError("Baison unavailable")


@pytest.mark.asyncio
async def test_sync_does_not_touch_database_when_fetch_fails(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(
        BaisonMemberService,
        "fetch_all_members",
        lambda self: (_ for _ in ()).throw(RuntimeError("Baison unavailable")),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        await sync_members(db)

    assert db.calls == []
