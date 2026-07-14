from pathlib import Path

from app.services.member_sales_service import build_vip_sales_summary


BACKEND = Path(__file__).resolve().parents[1]


def test_vip_sales_summary_uses_reliable_ticket_formulas():
    summary = build_vip_sales_summary({
        "total_sales": 1000,
        "vip_sales": 600,
        "vip_actual": 550,
        "vip_orders": 3,
        "vip_qty": 6,
        "vip_members": 2,
        "repeat_members": 1,
        "vip_standard": 800,
        "return_amount": 50,
        "return_orders": 1,
    })

    assert summary["vip_sales_amount"]["value"] == 600
    assert summary["vip_sales_ratio"]["value"] == 0.6
    assert summary["avg_order_value"]["value"] == 200
    assert summary["attachment_rate"]["value"] == 2
    assert summary["repurchase_rate"]["value"] == 0.5
    assert summary["avg_discount_rate"]["value"] == 0.75
    assert summary["return_rate"]["value"] == round(50 / 600, 4)


def test_unreliable_vip_dimensions_are_explicitly_pending():
    summary = build_vip_sales_summary({})
    assert summary["gross_profit"]["status"] == "pending_data"
    assert summary["gross_margin"]["status"] == "pending_data"
    assert summary["category_analysis"]["status"] == "pending_data"
    assert summary["style_analysis"]["status"] == "pending_data"


def test_member_api_keeps_phone_private_and_audits_explicit_access():
    source = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    assert "include_sensitive" in source
    assert "customer_phone" in source
    assert "sensitive_phone.view" in source
    assert "SysOperationLog" in source


def test_member_scope_and_balance_source_remain_fixed():
    member_service = (BACKEND / "app" / "integrations" / "baison" / "services" / "member_service.py").read_text(encoding="utf-8")
    member_api = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    assert 'raw.get("CZ_DQJE")' in member_service
    assert "ALLOWED_INVENTORY_CODES" in member_api
    assert "GREATEST(COALESCE(current_balance,0),0)" in member_api
    assert "current_balance<0" in member_api


def test_member_segments_have_persistence_scope_and_sensitive_audit():
    member_api = (BACKEND / "app" / "api" / "v1" / "member.py").read_text(encoding="utf-8")
    service = (BACKEND / "app" / "services" / "member_segment_service.py").read_text(encoding="utf-8")
    migration = (BACKEND / "alembic" / "versions" / "1e0f1a2b3c4d_member_segments.py").read_text(encoding="utf-8")

    assert "_allowed_member_codes" in member_api
    assert 'require_permission("member:segment:view")' in member_api
    assert 'require_permission("member:segment:rebuild")' in member_api
    assert 'require_permission("member:sensitive:export")' in member_api
    assert 'member:sensitive:view' in member_api
    assert "sensitive_balance.view" in member_api
    assert "sensitive_transaction.view" in member_api
    assert "sensitive_member.export" in member_api
    assert "dm_member_segment_snapshot" in migration
    assert "UNIQUE (calc_date, member_no)" in migration
    assert "ON CONFLICT (calc_date,member_no)" in service
    assert "responsibility_status=dm.dm_member_segment_snapshot.responsibility_status" in service
    assert "responsible_employee_no=dm.dm_member_segment_snapshot.responsible_employee_no" in service
    assert "s.metrics->>'current_balance'" in service
    assert "s.labels @> CAST(:label_filter AS jsonb)" in service
    assert "store_codes=codes" in member_api
    assert "MIN(biz_date) first_ticket_date" in service
    assert "idx_member_segment_member_date" in migration
    assert "NULLIF(s.metrics->>'last_consume_date','')::date" in service
    assert "m.current_balance DESC" not in service
    assert "m.total_amount DESC" not in service
    assert "from sqlalchemy.dialects.postgresql import JSONB" in (BACKEND / "app" / "models" / "dm.py").read_text(encoding="utf-8")
    assert (
        "COUNT(*) FILTER (WHERE sales_amount>0 AND "
        "biz_date>CAST(:calc_date AS date)-CAST(:period_days AS integer)) sales_order_count"
        in service
    )
    assert 'if _int(data.get("total_members")) == 0' in service
    assert "_redact_member_fields" in member_api
    assert 'member:sensitive:view' in member_api
    assert 'raise HTTPException(status_code=403, detail="无会员敏感数据查看权限")' in member_api


def test_daily_member_and_deposit_sync_rebuild_segments():
    member_sync = (BACKEND / "scripts" / "sync_baison_members.py").read_text(encoding="utf-8")
    deposit_sync = (BACKEND / "scripts" / "sync_baison_member_deposits.py").read_text(encoding="utf-8")
    assert "rebuild_member_segments" in member_sync
    assert "rebuild_member_segments" in deposit_sync
