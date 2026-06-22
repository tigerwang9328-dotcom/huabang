"""人事管理 API（员工/考勤/请假，数据来自钉钉同步表）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_permission
from app.core.database import get_db
from app.models.sys import SysUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/hr", tags=["人事管理"])


def _i(v):
    return int(v) if v is not None else 0


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
async def hr_attendance(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                        current_user: SysUser = Depends(require_permission("dashboard:view")),
                        db: AsyncSession = Depends(get_db)):
    total = (await db.execute(text("SELECT count(*) FROM hr_attendance_daily"))).scalar()
    rows = (await db.execute(text("""
        SELECT work_date, employee_name, department_name, normal_count, late_count,
               early_leave_count, missing_check_count, attendance_status
        FROM hr_attendance_daily ORDER BY work_date DESC, id DESC LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page - 1) * page_size})).mappings().all()
    items = [{"work_date": str(r["work_date"]), "employee_name": r["employee_name"],
              "department_name": r["department_name"], "normal_count": _i(r["normal_count"]),
              "late_count": _i(r["late_count"]), "early_leave_count": _i(r["early_leave_count"]),
              "missing_check_count": _i(r["missing_check_count"]),
              "attendance_status": r["attendance_status"]} for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})


@router.get("/leaves", response_model=ApiResponse)
async def hr_leaves(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    current_user: SysUser = Depends(require_permission("dashboard:view")),
                    db: AsyncSession = Depends(get_db)):
    total = (await db.execute(text(
        "SELECT count(*) FROM dingtalk_approval_instances WHERE category IN ('leave','business_trip')"))).scalar()
    rows = (await db.execute(text("""
        SELECT id, process_name, title, originator_name, originator_dept_name,
               category, status, result, create_time
        FROM dingtalk_approval_instances WHERE category IN ('leave','business_trip')
        ORDER BY id DESC LIMIT :limit OFFSET :offset
    """), {"limit": page_size, "offset": (page - 1) * page_size})).mappings().all()
    items = [{"id": r["id"], "process_name": r["process_name"], "title": r["title"],
              "originator_name": r["originator_name"], "department_name": r["originator_dept_name"],
              "category": r["category"], "status": r["status"], "result": r["result"],
              "create_time": r["create_time"].isoformat() if r["create_time"] else None} for r in rows]
    return ApiResponse.ok(data={"items": items, "total": _i(total), "page": page, "page_size": page_size})
