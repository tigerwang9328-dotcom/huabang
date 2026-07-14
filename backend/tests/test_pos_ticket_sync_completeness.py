import json
import inspect
from types import SimpleNamespace

import pytest

from app.integrations.baison.services import pos_ticket_service as ticket_module
from app.integrations.baison.services.pos_ticket_service import PosTicketService


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def request(self, method, params, timeout):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def api_response(*, page_total=1, total_result=1, rows=None, code="1"):
    rows = rows if rows is not None else [{"djbh": "T001"}]
    payload = {
        "page": {"pageTotal": page_total, "totalResult": total_result},
        "orderListGet": rows,
    }
    return SimpleNamespace(
        data={"code": code, "data": json.dumps(payload, ensure_ascii=False)},
        raw_response=json.dumps(payload, ensure_ascii=False),
    )


def build_service(monkeypatch, responses, *, can_start=True):
    service = object.__new__(PosTicketService)
    service.client = FakeClient(responses)
    service.batch_no = "PT202607140001"
    events = []

    async def ensure_tables():
        events.append(("ensure", {}))

    async def start_sync_run(start_dt, end_dt):
        events.append(("start", {"start": start_dt, "end": end_dt}))
        return can_start

    async def finish_sync_run(**kwargs):
        events.append(("finish", kwargs))

    async def save_batch(rows, start_dt, end_dt, fallback_date, page_no):
        events.append(("save", {"page": page_no, "rows": len(rows)}))
        return len(rows), len(rows)

    async def rebuild_dws_summary(start_time, end_time):
        events.append(("rebuild", {"start": start_time, "end": end_time}))
        return {"total_sales": 100}

    monkeypatch.setattr(service, "ensure_tables", ensure_tables)
    monkeypatch.setattr(service, "_start_sync_run", start_sync_run)
    monkeypatch.setattr(service, "_finish_sync_run", finish_sync_run)
    monkeypatch.setattr(service, "_save_batch", save_batch)
    monkeypatch.setattr(service, "rebuild_dws_summary", rebuild_dws_summary)
    return service, events


@pytest.mark.asyncio
async def test_complete_ticket_sync_marks_success_before_rebuilding(monkeypatch):
    service, events = build_service(monkeypatch, [api_response()])

    result = await service.sync_range("2026-07-06 00:00:00", "2026-07-06 23:59:59")

    assert result["ok"] is True
    assert [name for name, _ in events] == ["ensure", "start", "save", "finish", "rebuild"]
    finish = next(payload for name, payload in events if name == "finish")
    assert finish["status"] == "success"
    assert finish["completed_pages"] == 1
    assert finish["expected_pages"] == 1


@pytest.mark.asyncio
async def test_failed_ticket_page_marks_run_failed_and_skips_rebuild(monkeypatch):
    service, events = build_service(
        monkeypatch,
        [api_response(page_total=2, total_result=2), RuntimeError("network down")],
    )

    result = await service.sync_range("2026-07-06 00:00:00", "2026-07-06 23:59:59")

    assert result["ok"] is False
    assert "network down" in result["error"]
    assert "rebuild" not in [name for name, _ in events]
    finish = next(payload for name, payload in events if name == "finish")
    assert finish["status"] == "failed"
    assert finish["completed_pages"] == 1
    assert finish["expected_pages"] == 2


@pytest.mark.asyncio
async def test_max_pages_cannot_mark_partial_ticket_sync_as_complete(monkeypatch):
    service, events = build_service(
        monkeypatch,
        [api_response(page_total=3, total_result=3)],
    )

    result = await service.sync_range(
        "2026-07-06 00:00:00",
        "2026-07-06 23:59:59",
        max_pages=1,
    )

    assert result["ok"] is False
    assert result["error"] == "同步页数受限，批次数据不完整"
    assert "rebuild" not in [name for name, _ in events]
    finish = next(payload for name, payload in events if name == "finish")
    assert finish["status"] == "failed"


@pytest.mark.asyncio
async def test_short_final_page_cannot_claim_complete_total_result(monkeypatch):
    service, events = build_service(
        monkeypatch,
        [api_response(page_total=1, total_result=2, rows=[{"djbh": "T001"}])],
    )

    result = await service.sync_range("2026-07-06 00:00:00", "2026-07-06 23:59:59")

    assert result["ok"] is False
    assert result["error"] == "百胜小票返回数量不完整: 1/2"
    assert "rebuild" not in [name for name, _ in events]


def test_batch_number_is_unique_for_concurrent_service_instances(monkeypatch):
    monkeypatch.setattr(ticket_module, "BaisonClient", lambda: object())

    first = PosTicketService()
    second = PosTicketService()

    assert first.batch_no != second.batch_no


@pytest.mark.asyncio
async def test_overlapping_sync_is_rejected_before_any_page_is_written(monkeypatch):
    service, events = build_service(monkeypatch, [], can_start=False)

    result = await service.sync_range("2026-07-06 00:00:00", "2026-07-06 23:59:59")

    assert result == {
        "ok": False,
        "method": "pos.qtlsd.list_get",
        "batch_no": "PT202607140001",
        "error": "已有百胜小票同步正在运行，请稍后重试",
    }
    assert [name for name, _ in events] == ["ensure", "start"]


def test_page_writes_and_finish_are_fenced_by_the_active_run_row():
    save_source = inspect.getsource(PosTicketService._save_batch)
    finish_source = inspect.getsource(PosTicketService._finish_sync_run)
    start_source = inspect.getsource(PosTicketService._start_sync_run)

    assert "FOR UPDATE" in save_source
    assert "status != \"running\"" in save_source
    assert "updated_at=now()" in save_source
    assert "AND status='running'" in finish_source
    assert "updated_at < now() - INTERVAL '2 hours'" in start_source
