"""人事管理 API（员工/考勤/请假，数据来自钉钉同步表）。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/hr", tags=["人事管理"])


def _i(v):
    return int(v) if v is not None else 0


def _s(v):
    return str(v) if v is not None else ""


def _status_label(row) -> str:
    if _i(row["leave_count"]) > 0:
        return "请假"
    if _i(row["missing_check_count"]) > 0:
        return "缺卡"
    if _i(row["late_count"]) > 0:
        return "迟到"
    if _i(row["early_leave_count"]) > 0:
        return "早退"
    return "正常"


class DingtalkSyncRequest(BaseModel):
    scope: str = Field("attendance", pattern="^(employees|attendance|approvals|all)$")
    days: int = Field(7, ge=1, le=30)
    dry_run: bool = False


@router.get("/overview", response_model=ApiResponse)
async def hr_overview(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    """人事汇总：在职人数、今日出勤/迟到/早退/缺卡/请假、部门出勤、最近考勤异常。"""
    headcount = (await db.execute(text(
        "SELECT count(*) FROM dingtalk_employees WHERE active = true"))).scalar()

    today = (await db.execute(text("""
        SELECT
          count(DISTINCT dingtalk_user_id) AS att_users,
          coalesce(sum(late_count),0) AS late,
          coalesce(sum(early_leave_count),0) AS early,
          coalesce(sum(missing_check_count),0) AS missing,
          coalesce(sum(leave_count),0) AS leave_cnt
        FROM hr_attendance_daily WHERE work_date = current_date
    """))).mappings().first()

    leave_today = (await db.execute(text("""
        SELECT count(*) FROM dingtalk_approval_instances
        WHERE category='leave' AND status IN ('NEW','RUNNING','COMPLETED')
          AND create_time::date = current_date
    """))).scalar()

    dept_att = (await db.execute(text("""
        SELECT coalesce(department_name,'未知') AS dept,
               count(DISTINCT dingtalk_user_id) AS users,
               coalesce(sum(late_count),0) AS late,
               coalesce(sum(missing_check_count),0) AS missing
        FROM hr_attendance_daily WHERE work_date = current_date
        GROUP BY department_name ORDER BY users DESC LIMIT 10
    """))).mappings().all()

    abnormal = (await db.execute(text("""
        SELECT work_date, dingtalk_user_id, employee_name, late_count,
               early_leave_count, missing_check_count, attendance_status
        FROM hr_attendance_daily
        WHERE attendance_status = 'abnormal'
        ORDER BY work_date DESC, id DESC LIMIT 10
    """))).mappings().all()

    return ApiResponse.ok(data={
        "headcount": _i(headcount),
        "today": {
            "attendance_count": _i(today["att_users"]),
            "late_count": _i(today["late"]),
            "early_leave_count": _i(today["early"]),
            "missing_check_count": _i(today["missing"]),
            "leave_count": _i(leave_today),
        },
        "department_attendance": [
            {"department": r["dept"], "users": _i(r["users"]),
             "late": _i(r["late"]), "missing": _i(r["missing"])} for r in dept_att
        ],
        "recent_abnormal": [
            {"work_date": str(r["work_date"]), "employee_name": r["employee_name"],
             "late_count": _i(r["late_count"]), "early_leave_count": _i(r["early_leave_count"]),
             "missing_check_count": _i(r["missing_check_count"]), "status": r["attendance_status"]}
            for r in abnormal
        ],
    })


@router.get("/employees", response_model=ApiResponse)
async def hr_employees(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                       current_user: SysUser = Depends(require_permission("dashboard:view")),
                       db: AsyncSession = Depends(get_db)):
    total = (await db.execute(text("SELECT count(*) FROM dingtalk_employees"))).scalar()
    rows = (await db.execute(text("""
        SELECT id, name, mobile, position, job_number, email, active, department_names
        FROM dingtalk_employees ORDER BY id DESC LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page - 1) * page_size})).mappings().all()
    items = [{"id": r["id"], "name": r["name"], "mobile": r["mobile"], "position": r["position"],
              "job_number": r["job_number"], "email": r["email"], "active": r["active"]} for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})


@router.get("/attendance", response_model=ApiResponse)
async def hr_attendance(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    work_date: Optional[date] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    if work_date:
        filters.append("work_date = :work_date")
        params["work_date"] = work_date
    if date_from:
        filters.append("work_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("work_date <= :date_to")
        params["date_to"] = date_to
    if department and department != "全部":
        filters.append("coalesce(department_name,'未知') = :department")
        params["department"] = department
    if keyword:
        filters.append("(employee_name ILIKE :keyword OR department_name ILIKE :keyword OR dingtalk_user_id ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if status and status != "全部":
        if status == "正常":
            filters.append("coalesce(late_count,0)=0 AND coalesce(early_leave_count,0)=0 AND coalesce(missing_check_count,0)=0 AND coalesce(leave_count,0)=0")
        elif status == "迟到":
            filters.append("coalesce(late_count,0) > 0")
        elif status == "早退":
            filters.append("coalesce(early_leave_count,0) > 0")
        elif status == "缺卡":
            filters.append("coalesce(missing_check_count,0) > 0")
        elif status == "请假":
            filters.append("coalesce(leave_count,0) > 0")
        elif status == "异常":
            filters.append("attendance_status = 'abnormal'")

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    total = (await db.execute(text(f"SELECT count(*) FROM hr_attendance_daily {where}"), params)).scalar()
    rows = (await db.execute(text(f"""
        SELECT id, work_date, dingtalk_user_id, employee_name, coalesce(department_name,'未知') AS department_name,
               normal_count, late_count, early_leave_count, missing_check_count, leave_count, attendance_status
        FROM hr_attendance_daily
        {where}
        ORDER BY work_date DESC, id DESC LIMIT :limit OFFSET :offset
    """), params)).mappings().all()

    items = [{
        "id": r["id"],
        "work_date": str(r["work_date"]),
        "dingtalk_user_id": r["dingtalk_user_id"],
        "employee_name": r["employee_name"] or r["dingtalk_user_id"],
        "department_name": r["department_name"],
        "normal_count": _i(r["normal_count"]),
        "late_count": _i(r["late_count"]),
        "early_leave_count": _i(r["early_leave_count"]),
        "missing_check_count": _i(r["missing_check_count"]),
        "leave_count": _i(r["leave_count"]),
        "attendance_status": r["attendance_status"],
        "status_label": _status_label(r),
    } for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})


@router.get("/attendance/summary", response_model=ApiResponse)
async def hr_attendance_summary(
    work_date: Optional[date] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    stat_date_sql = "CAST(:work_date AS date)" if work_date else "current_date"
    params = {"work_date": work_date} if work_date else {}
    summary = (await db.execute(text(f"""
        SELECT
          count(*) AS total_rows,
          count(DISTINCT dingtalk_user_id) AS checked_users,
          coalesce(sum(late_count),0) AS late,
          coalesce(sum(early_leave_count),0) AS early,
          coalesce(sum(missing_check_count),0) AS missing,
          coalesce(sum(leave_count),0) AS leave_cnt,
          coalesce(sum(normal_count),0) AS normal_checks
        FROM hr_attendance_daily WHERE work_date = {stat_date_sql}
    """), params)).mappings().first()
    headcount = (await db.execute(text("SELECT count(*) FROM dingtalk_employees WHERE active = true"))).scalar()
    approvals = (await db.execute(text(f"""
        SELECT count(*) FROM dingtalk_approval_instances
        WHERE category IN ('leave','business_trip','attendance') AND create_time::date = {stat_date_sql}
    """), params)).scalar()
    pending = (await db.execute(text("""
        SELECT count(*) FROM dingtalk_approval_instances
        WHERE category IN ('leave','business_trip','attendance') AND status IN ('NEW','RUNNING')
    """))).scalar()
    sync_info = (await db.execute(text("""
        SELECT max(updated_at) AS last_sync FROM hr_attendance_daily
    """))).mappings().first()

    return ApiResponse.ok(data={
        "headcount": _i(headcount),
        "checked_users": _i(summary["checked_users"]),
        "unchecked_users": max(_i(headcount) - _i(summary["checked_users"]), 0),
        "late_count": _i(summary["late"]),
        "early_leave_count": _i(summary["early"]),
        "missing_check_count": _i(summary["missing"]),
        "leave_count": _i(summary["leave_cnt"]),
        "normal_checks": _i(summary["normal_checks"]),
        "approval_count": _i(approvals),
        "pending_approval_count": _i(pending),
        "last_sync_at": sync_info["last_sync"].isoformat() if sync_info and sync_info["last_sync"] else None,
    })


@router.get("/attendance/departments", response_model=ApiResponse)
async def hr_attendance_departments(
    work_date: Optional[date] = Query(None),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    stat_date_sql = "CAST(:work_date AS date)" if work_date else "current_date"
    params = {"work_date": work_date} if work_date else {}
    rows = (await db.execute(text(f"""
        SELECT coalesce(department_name,'未知') AS department,
               count(DISTINCT dingtalk_user_id) AS users,
               coalesce(sum(late_count),0) AS late,
               coalesce(sum(early_leave_count),0) AS early,
               coalesce(sum(missing_check_count),0) AS missing,
               coalesce(sum(leave_count),0) AS leave_cnt
        FROM hr_attendance_daily
        WHERE work_date = {stat_date_sql}
        GROUP BY coalesce(department_name,'未知')
        ORDER BY users DESC, department ASC
    """), params)).mappings().all()
    items = []
    for r in rows:
        abnormal = _i(r["late"]) + _i(r["early"]) + _i(r["missing"]) + _i(r["leave_cnt"])
        users = _i(r["users"])
        items.append({
            "department": r["department"],
            "users": users,
            "late": _i(r["late"]),
            "early": _i(r["early"]),
            "missing": _i(r["missing"]),
            "leave": _i(r["leave_cnt"]),
            "attendance_rate": round(max(users - abnormal, 0) / users * 100, 1) if users else 0,
        })
    return ApiResponse.ok(data={"items": items})


@router.get("/approvals", response_model=ApiResponse)
async def hr_approvals(
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    if category and category != "all":
        filters.append("category = :category")
        params["category"] = category
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    total = (await db.execute(text(f"SELECT count(*) FROM dingtalk_approval_instances {where}"), params)).scalar()
    rows = (await db.execute(text(f"""
        SELECT a.id, a.process_name, a.title, coalesce(a.originator_name, e.name) AS originator_name,
               a.originator_dept_name, a.category, a.status, a.result, a.amount, a.create_time, a.finish_time
        FROM dingtalk_approval_instances a
        LEFT JOIN dingtalk_employees e ON e.dingtalk_user_id = a.originator_user_id
        {where}
        ORDER BY a.create_time DESC NULLS LAST, a.id DESC LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
    items = [{
        "id": r["id"],
        "process_name": r["process_name"],
        "title": r["title"],
        "originator_name": r["originator_name"],
        "department_name": r["originator_dept_name"],
        "category": r["category"],
        "status": r["status"],
        "result": r["result"],
        "amount": float(r["amount"]) if r["amount"] is not None else None,
        "create_time": r["create_time"].isoformat() if r["create_time"] else None,
        "finish_time": r["finish_time"].isoformat() if r["finish_time"] else None,
    } for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})


@router.get("/departments", response_model=ApiResponse)
async def hr_departments(
    current_user: SysUser = Depends(require_permission("dashboard:view")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text("""
        SELECT name FROM dingtalk_departments WHERE name IS NOT NULL
        UNION
        SELECT department_name AS name FROM hr_attendance_daily WHERE department_name IS NOT NULL
        ORDER BY name
    """))).mappings().all()
    return ApiResponse.ok(data={"items": [_s(r["name"]) for r in rows if r["name"]]})


@router.post("/sync-dingtalk", response_model=ApiResponse)
async def sync_dingtalk_hr(
    body: DingtalkSyncRequest,
    current_user: SysUser = Depends(require_permission("dingtalk:config")),
):
    from app.modules.dingtalk.sync import approvals, attendance, employees

    result = {}
    if body.scope in ("employees", "all"):
        result["employees"] = await employees.run(dry_run=body.dry_run)
    if body.scope in ("attendance", "all"):
        result["attendance"] = await attendance.run(days=min(body.days, 7), dry_run=body.dry_run)
    if body.scope in ("approvals", "all"):
        result["approvals"] = await approvals.run(days=body.days, dry_run=body.dry_run)
    return ApiResponse.ok(data=result, message="钉钉人事同步完成")


@router.get("/leaves", response_model=ApiResponse)
async def hr_leaves(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    current_user: SysUser = Depends(require_permission("dashboard:view")),
                    db: AsyncSession = Depends(get_db)):
    total = (await db.execute(text(
        "SELECT count(*) FROM dingtalk_approval_instances WHERE category IN ('leave','business_trip')"))).scalar()
    rows = (await db.execute(text("""
        SELECT a.id, a.process_name, a.title, coalesce(a.originator_name, e.name) AS originator_name,
               a.originator_dept_name, a.category, a.status, a.result, a.create_time
        FROM dingtalk_approval_instances a
        LEFT JOIN dingtalk_employees e ON e.dingtalk_user_id = a.originator_user_id
        WHERE a.category IN ('leave','business_trip')
        ORDER BY a.id DESC LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page - 1) * page_size})).mappings().all()
    items = [{"id": r["id"], "process_name": r["process_name"], "title": r["title"],
              "originator_name": r["originator_name"], "department_name": r["originator_dept_name"],
              "category": r["category"], "status": r["status"], "result": r["result"],
              "create_time": r["create_time"].isoformat() if r["create_time"] else None} for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})
