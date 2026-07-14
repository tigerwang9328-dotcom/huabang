"""Evidence-backed VIP action candidates built on the existing task workflow."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import AppActionTask


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _guide_store_codes(user: Mapping[str, Any]) -> set[str]:
    return {str(code).strip().upper() for code in user.get("store_codes") or [] if str(code or "").strip()}


def _contact_script(snapshot: Mapping[str, Any], reason: str, products: list[dict[str, Any]]) -> str:
    balance = _num((snapshot.get("metrics") or {}).get("current_balance"))
    product_text = "、".join(str(item.get("product_name") or item.get("product_code") or "") for item in products[:2] if item)
    parts = ["您好，想跟您做一次会员关怀回访。"]
    if reason:
        parts.append(f"系统提示您近期{reason}，想了解您的穿着需求。")
    if balance > 0:
        parts.append(f"您当前会员余额约{balance:.0f}元，可到店正常使用。")
    if product_text:
        parts.append(f"结合您过往偏好，店内可重点看看{product_text}。")
    parts.append("具体联系内容和优惠承诺请由主管确认后再发送。")
    return "".join(parts)


def build_member_action_candidate(
    snapshot: Mapping[str, Any],
    *,
    available_product_codes: set[str] | None = None,
    guide_users: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one non-executable contact suggestion from a saved segment snapshot."""
    reasons = list(snapshot.get("wakeup_reasons") or snapshot.get("risks") or [])
    reason_names = [str(item.get("name") or item.get("code") or "") for item in reasons if isinstance(item, Mapping)]
    contact_reason = "、".join(value for value in reason_names if value) or "会员需要定期关怀"
    products = [dict(item) for item in snapshot.get("suggested_products") or [] if isinstance(item, Mapping)]
    if available_product_codes is not None:
        products = [item for item in products if str(item.get("product_code") or "") in available_product_codes]
    candidate_guides = sorted({str(value).strip() for value in snapshot.get("candidate_guide_ids") or [] if str(value or "").strip()})
    suggested_assignee = None
    users = guide_users or {}
    if len(candidate_guides) == 1:
        employee_no = candidate_guides[0]
        user = users.get(employee_no)
        store_code = str(snapshot.get("store_code") or "").upper()
        if user and store_code in _guide_store_codes(user):
            suggested_assignee = {
                "user_id": int(user["user_id"]),
                "employee_no": employee_no,
                "real_name": str(user.get("real_name") or employee_no),
            }
    return _json_value({
        "snapshot_id": int(snapshot.get("id") or 0),
        "calc_date": str(snapshot.get("calc_date") or "")[:10],
        "member_no": str(snapshot.get("member_no") or ""),
        "member_name": str(snapshot.get("member_name") or ""),
        "store_code": str(snapshot.get("store_code") or "").upper(),
        "contact_reason": contact_reason,
        "recommended_products": products[:3],
        "suggested_script": _contact_script(snapshot, contact_reason, products),
        "suggested_assignee": suggested_assignee,
        "candidate_guide_ids": candidate_guides,
        "responsibility_status": "suggested" if suggested_assignee else "unconfirmed",
        "requires_human_confirmation": True,
        "data_evidence": {
            "source": "dm.dm_member_segment_snapshot",
            "snapshot_id": int(snapshot.get("id") or 0),
            "rule_version": snapshot.get("rule_version"),
            "source_updated_at": snapshot.get("source_updated_at"),
            "risks": reasons,
            "metrics": dict(snapshot.get("metrics") or {}),
            "preferences": list(snapshot.get("preferences") or []),
        },
    })


def evaluate_member_action_outcome(
    followup: Mapping[str, Any] | None,
    *,
    linked_ticket_verified: bool,
    verified_ticket_amount: float | None = None,
    has_unlinked_repurchase: bool,
) -> dict[str, Any]:
    data = dict(followup or {})
    contacted = bool(data.get("contacted"))
    arrived = bool(data.get("arrived"))
    claimed_conversion = bool(data.get("converted"))
    linked_ticket_no = str(data.get("linked_ticket_no") or "").strip() or None
    attributed = bool(claimed_conversion and linked_ticket_no and linked_ticket_verified)
    if attributed:
        attribution = "action_conversion"
    elif claimed_conversion:
        attribution = "unverified_conversion"
    elif has_unlinked_repurchase:
        attribution = "natural_repurchase"
    else:
        attribution = "no_conversion"
    return {
        "contacted": contacted,
        "arrived": arrived,
        "claimed_conversion": claimed_conversion,
        "attributed_conversion": attributed,
        "attributed_amount": round(_num(verified_ticket_amount), 2) if attributed else 0.0,
        "reported_amount": round(_num(data.get("conversion_amount")), 2),
        "linked_ticket_no": linked_ticket_no,
        "linked_ticket_verified": linked_ticket_verified,
        "natural_repurchase": attribution == "natural_repurchase",
        "attribution": attribution,
    }


def summarize_member_action_outcomes(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in items]
    confirmed = [item for item in rows if item.get("confirmed")]
    contacted = [item for item in confirmed if item.get("contacted")]
    arrived = [item for item in contacted if item.get("arrived")]
    converted = [item for item in contacted if item.get("attributed_conversion")]
    natural = [item for item in confirmed if item.get("natural_repurchase")]
    return {
        "total_actions": len(rows),
        "confirmed_actions": len(confirmed),
        "contacted_actions": len(contacted),
        "arrived_actions": len(arrived),
        "converted_actions": len(converted),
        "natural_repurchase_actions": len(natural),
        "contact_rate": len(contacted) / len(confirmed) if confirmed else 0.0,
        "arrival_rate": len(arrived) / len(contacted) if contacted else 0.0,
        "conversion_rate": len(converted) / len(contacted) if contacted else 0.0,
        "attributed_sales": round(sum(_num(item.get("attributed_amount")) for item in converted), 2),
    }


async def _latest_snapshot_date(db: AsyncSession, store_codes: list[str]) -> date | None:
    return (await db.execute(text("""
        SELECT MAX(calc_date) FROM dm.dm_member_segment_snapshot
        WHERE store_code=ANY(:store_codes)
    """), {"store_codes": store_codes})).scalar()


async def generate_member_action_drafts(
    db: AsyncSession,
    *,
    store_codes: Iterable[str],
    calc_date: date | None = None,
    creator_id: int | None = None,
) -> dict[str, Any]:
    codes = sorted({str(code).upper() for code in store_codes})
    target_date = calc_date or await _latest_snapshot_date(db, codes)
    if not target_date:
        return {"calc_date": None, "candidate_count": 0, "created_count": 0, "status": "pending_data"}
    locked = (await db.execute(text(
        "SELECT pg_try_advisory_xact_lock(hashtext('member_action_drafts'), :lock_date)"
    ), {"lock_date": int(target_date.strftime("%Y%m%d"))})).scalar()
    if not locked:
        return {"calc_date": target_date.isoformat(), "candidate_count": 0, "created_count": 0, "status": "locked"}
    rows = (await db.execute(text("""
        SELECT s.id,s.calc_date,s.member_no,m.member_name,s.store_code,s.risks,s.metrics,
               s.wakeup_reasons,s.preferences,s.suggested_products,s.candidate_guide_ids,
               s.rule_version,s.source_updated_at,s.wakeup_priority
        FROM dm.dm_member_segment_snapshot s
        JOIN dim.dim_member m ON m.member_no=s.member_no
        WHERE s.calc_date=:calc_date AND s.store_code=ANY(:store_codes)
          AND s.is_wakeup_candidate=true
        ORDER BY COALESCE(s.wakeup_priority,99),s.id
    """), {"calc_date": target_date, "store_codes": codes})).mappings().all()
    if creator_id is None:
        creator_id = (await db.execute(text("""
            SELECT id FROM sys.sys_user
            WHERE is_admin=true AND status=1 AND is_deleted=false ORDER BY id LIMIT 1
        """))).scalar()
    if creator_id is None:
        return {"calc_date": target_date.isoformat(), "candidate_count": len(rows), "created_count": 0, "status": "pending_data", "reason": "缺少系统任务创建账号"}

    candidate_guide_ids = sorted({str(value) for row in rows for value in (row["candidate_guide_ids"] or [])})
    guide_rows = (await db.execute(text("""
        SELECT u.id user_id,u.employee_no,u.real_name,
               array_remove(array_agg(DISTINCT COALESCE(us.store_code,u.store_code)),NULL) store_codes
        FROM sys.sys_user u
        LEFT JOIN sys.sys_user_store us ON us.user_id=u.id
        WHERE u.employee_no=ANY(:employee_nos) AND u.status=1 AND u.is_deleted=false
        GROUP BY u.id,u.employee_no,u.real_name
    """), {"employee_nos": candidate_guide_ids or ["__NONE__"]})).mappings().all()
    guide_users = {str(row["employee_no"]): dict(row) for row in guide_rows}
    product_codes = sorted({str(item.get("product_code")) for row in rows for item in (row["suggested_products"] or []) if item.get("product_code")})
    inventory_rows = (await db.execute(text("""
        SELECT UPPER(warehouse_code) store_code,product_code
        FROM dwd.v_apparel_inventory_balance
        WHERE product_code=ANY(:product_codes) AND qty>0 AND UPPER(warehouse_code)=ANY(:store_codes)
        GROUP BY UPPER(warehouse_code),product_code
    """), {"product_codes": product_codes or ["__NONE__"], "store_codes": codes})).mappings().all()
    available_by_store: dict[str, set[str]] = {}
    for inventory_row in inventory_rows:
        available_by_store.setdefault(str(inventory_row["store_code"]), set()).add(str(inventory_row["product_code"]))
    open_members = set((await db.execute(text("""
        SELECT data_evidence->'member_action'->>'member_no'
        FROM app.app_action_task
        WHERE source_type='member_action' AND is_deleted=false
          AND status NOT IN ('closed','cancelled')
    """))).scalars().all())
    existing_source_ids = set((await db.execute(text("""
        SELECT source_id FROM app.app_action_task
        WHERE source_type='member_action' AND source_id IS NOT NULL
    """))).scalars().all())

    created = 0
    for row in rows:
        if int(row["id"]) in existing_source_ids or row["member_no"] in open_members:
            continue
        candidate = build_member_action_candidate(
            dict(row),
            available_product_codes=available_by_store.get(str(row["store_code"]).upper(), set()),
            guide_users=guide_users,
        )
        assignee = candidate["suggested_assignee"]
        risk_levels = {str(item.get("severity") or "") for item in row["risks"] or []}
        task = AppActionTask(
            task_no="MV" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6].upper(),
            title=f"VIP关怀：{row['member_no']} · {candidate['contact_reason']}",
            description="根据已保存的会员分层证据生成联系建议，联系前须由主管确认责任人和话术。",
            data_evidence={"member_action": candidate},
            data_evidence_text=f"{candidate['contact_reason']}；规则版本 {row['rule_version']}；快照日期 {target_date}",
            suggested_actions=[
                {"type": "contact_script", "content": candidate["suggested_script"]},
                {"type": "recommended_products", "items": candidate["recommended_products"]},
            ],
            review_metrics=["是否联系", "是否到店", "是否成交", "关联百胜小票", "成交金额", "下次跟进时间"],
            feedback_requirement="记录联系、到店、成交、未成交原因和下次跟进时间；成交须关联百胜小票后才计入行动转化。",
            source_type="member_action",
            source_id=int(row["id"]),
            related_store_code=row["store_code"],
            related_date=target_date,
            assignee_id=assignee["user_id"] if assignee else None,
            assignee_name=assignee["real_name"] if assignee else None,
            assignee_role=None,
            creator_id=creator_id,
            due_date=target_date + timedelta(days=3),
            status="draft",
            priority=max(5, 10 - int(row["wakeup_priority"] or 3)),
            risk_level="critical" if "critical" in risk_levels else "high" if "risk" in risk_levels else "medium",
            requires_human_confirm=True,
        )
        db.add(task)
        existing_source_ids.add(int(row["id"]))
        open_members.add(row["member_no"])
        created += 1
    await db.flush()
    return {
        "calc_date": target_date.isoformat(),
        "candidate_count": len(rows),
        "created_count": created,
        "skipped_open_count": len(rows) - created,
        "status": "ready",
    }


async def list_member_actions(
    db: AsyncSession,
    *,
    store_codes: Iterable[str],
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    codes = sorted({str(code).upper() for code in store_codes})
    params: dict[str, Any] = {"store_codes": codes, "limit": page_size, "offset": (page - 1) * page_size}
    status_sql = ""
    if status:
        status_sql = " AND status=:status"
        params["status"] = status
    keyword_sql = ""
    if keyword and keyword.strip():
        keyword_sql = " AND (title ILIKE :keyword OR COALESCE(data_evidence->'member_action'->>'member_no','') ILIKE :keyword)"
        params["keyword"] = f"%{keyword.strip()}%"
    total = (await db.execute(text(f"""
        SELECT COUNT(*) FROM app.app_action_task
        WHERE source_type='member_action' AND is_deleted=false
          AND related_store_code=ANY(:store_codes){status_sql}{keyword_sql}
    """), params)).scalar() or 0
    rows = (await db.execute(text(f"""
        SELECT id,task_no,title,status,priority,risk_level,assignee_id,assignee_name,
               due_date,related_store_code,related_date,data_evidence,confirmed_at,created_at
        FROM app.app_action_task
        WHERE source_type='member_action' AND is_deleted=false
          AND related_store_code=ANY(:store_codes){status_sql}{keyword_sql}
        ORDER BY CASE status WHEN 'draft' THEN 1 WHEN 'pending' THEN 2 WHEN 'processing' THEN 3 ELSE 4 END,
                 priority DESC,created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["member_action"] = (item.pop("data_evidence") or {}).get("member_action") or {}
        for key in ("due_date", "related_date"):
            item[key] = str(item.get(key) or "")[:10] or None
        for key in ("confirmed_at", "created_at"):
            item[key] = str(item.get(key) or "") or None
        items.append(item)
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


async def get_member_action_overview(
    db: AsyncSession,
    *,
    store_codes: Iterable[str],
    days: int = 30,
) -> dict[str, Any]:
    codes = sorted({str(code).upper() for code in store_codes})
    rows = (await db.execute(text("""
        SELECT t.id,t.status,t.confirmed_at,t.related_store_code,t.data_evidence,
               f.request_id,f.metrics_after
        FROM app.app_action_task t
        LEFT JOIN LATERAL (
          SELECT request_id,metrics_after FROM app.app_task_feedback
          WHERE task_id=t.id ORDER BY created_at DESC,id DESC LIMIT 1
        ) f ON true
        WHERE t.source_type='member_action' AND t.is_deleted=false
          AND t.related_store_code=ANY(:store_codes)
          AND t.created_at>=now()-CAST(:days AS integer)*INTERVAL '1 day'
        ORDER BY t.id
    """), {"store_codes": codes, "days": days})).mappings().all()
    ticket_requests: list[dict[str, Any]] = []
    for row in rows:
        action = (row["data_evidence"] or {}).get("member_action") or {}
        followup = (row["metrics_after"] or {}).get("member_followup") or {}
        if followup.get("linked_ticket_no"):
            ticket_requests.append({
                "task_id": int(row["id"]),
                "ticket_no": str(followup["linked_ticket_no"]),
                "member_no": str(action.get("member_no") or ""),
                "store_code": str(row["related_store_code"] or "").upper(),
            })
    verified_ticket_amounts: dict[int, float] = {}
    if ticket_requests:
        ticket_rows = (await db.execute(text("""
            SELECT ticket_no,UPPER(store_code) store_code,biz_date,COALESCE(sales_amount,0) sales_amount,
                   NULLIF(BTRIM(COALESCE(NULLIF(vip_code::text,''),NULLIF(customer_code::text,''),'')),'') member_no
            FROM dwd.dwd_pos_ticket
            WHERE ticket_no=ANY(:ticket_nos) AND COALESCE(is_void,false)=false AND COALESCE(is_pending,false)=false
        """), {"ticket_nos": sorted({item["ticket_no"] for item in ticket_requests})})).mappings().all()
        ticket_lookup = {
            (str(item["ticket_no"]), str(item["store_code"]), str(item["member_no"])): item
            for item in ticket_rows
        }
        row_by_id = {int(item["id"]): item for item in rows}
        for request in ticket_requests:
            ticket = ticket_lookup.get((request["ticket_no"], request["store_code"], request["member_no"]))
            task_row = row_by_id[request["task_id"]]
            if not ticket or not task_row["confirmed_at"]:
                continue
            confirmed_date = task_row["confirmed_at"].astimezone(ZoneInfo("Asia/Shanghai")).date()
            if ticket["biz_date"] >= confirmed_date and _num(ticket["sales_amount"]) > 0:
                verified_ticket_amounts[request["task_id"]] = _num(ticket["sales_amount"])

    natural_repurchase_task_ids: set[int] = set()
    confirmed_rows = [row for row in rows if row["confirmed_at"] and ((row["data_evidence"] or {}).get("member_action") or {}).get("member_no")]
    if confirmed_rows:
        member_nos = sorted({str(((row["data_evidence"] or {}).get("member_action") or {})["member_no"]) for row in confirmed_rows})
        min_date = min(row["confirmed_at"].astimezone(ZoneInfo("Asia/Shanghai")).date() for row in confirmed_rows)
        purchase_rows = (await db.execute(text("""
            SELECT ticket_no,UPPER(store_code) store_code,biz_date,
                   NULLIF(BTRIM(COALESCE(NULLIF(vip_code::text,''),NULLIF(customer_code::text,''),'')),'') member_no
            FROM dwd.dwd_pos_ticket
            WHERE NULLIF(BTRIM(COALESCE(NULLIF(vip_code::text,''),NULLIF(customer_code::text,''),'')),'')=ANY(:member_nos)
              AND UPPER(store_code)=ANY(:store_codes) AND biz_date>:min_date
              AND COALESCE(sales_amount,0)>0 AND COALESCE(is_void,false)=false AND COALESCE(is_pending,false)=false
        """), {"member_nos": member_nos, "store_codes": codes, "min_date": min_date})).mappings().all()
        for row in confirmed_rows:
            action = (row["data_evidence"] or {}).get("member_action") or {}
            followup = (row["metrics_after"] or {}).get("member_followup") or {}
            confirmed_date = row["confirmed_at"].astimezone(ZoneInfo("Asia/Shanghai")).date()
            if any(
                str(purchase["member_no"]) == str(action["member_no"])
                and purchase["biz_date"] > confirmed_date
                and str(purchase["ticket_no"]) != str(followup.get("linked_ticket_no") or "")
                for purchase in purchase_rows
            ):
                natural_repurchase_task_ids.add(int(row["id"]))

    outcomes = []
    for row in rows:
        action = (row["data_evidence"] or {}).get("member_action") or {}
        followup = (row["metrics_after"] or {}).get("member_followup") or {}
        outcome = evaluate_member_action_outcome(
            followup,
            linked_ticket_verified=int(row["id"]) in verified_ticket_amounts,
            verified_ticket_amount=verified_ticket_amounts.get(int(row["id"])),
            has_unlinked_repurchase=int(row["id"]) in natural_repurchase_task_ids,
        )
        outcome["confirmed"] = row["confirmed_at"] is not None
        outcomes.append(outcome)
    summary = summarize_member_action_outcomes(outcomes)
    summary.update({
        "draft_actions": sum(1 for row in rows if row["status"] == "draft"),
        "pending_followup_actions": sum(1 for row in rows if row["confirmed_at"] and not row["metrics_after"]),
        "window_days": days,
        "attribution_note": "只有反馈关联且核验通过的百胜小票计入行动成交；其他后续消费列为自然复购。",
    })
    return summary
