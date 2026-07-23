"""
店铺经营日报 — 计算用店铺组管理 API  /api/v1/finance/store-report-groups/*
（与企微推送组 biz_store_group_bindings 无关）
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.v1.deps import get_db, get_current_user
from app.models.sys import SysUser as User

router = APIRouter(prefix="/finance/store-report-groups")


async def _descendant_ids(db: AsyncSession, root_id: int) -> set:
    """返回 root_id 及其所有后代组 id（用于防环：父不能设为自身或后代）"""
    r = await db.execute(text("SELECT id, parent_group_id FROM biz_store_report_groups"))
    children = {}
    for row in r.fetchall():
        children.setdefault(row.parent_group_id, []).append(int(row.id))
    out, stack = set(), [root_id]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


async def _validate_parent(db: AsyncSession, group_id, parent_group_id):
    """校验父组合法：存在、非自身、非自身后代"""
    if parent_group_id is None:
        return
    parent_group_id = int(parent_group_id)
    if group_id is not None and parent_group_id == int(group_id):
        raise HTTPException(status_code=409, detail="父组不能是自身")
    exists = await db.execute(text("SELECT 1 FROM biz_store_report_groups WHERE id=:id"), {"id": parent_group_id})
    if not exists.first():
        raise HTTPException(status_code=422, detail="父组不存在")
    if group_id is not None:
        desc = await _descendant_ids(db, int(group_id))
        if parent_group_id in desc:
            raise HTTPException(status_code=409, detail="父组不能设为自身的子孙组（会成环）")


async def _check_occupied(db: AsyncSession, store_ids: list[int], exclude_group_id: Optional[int]):
    """返回 store_ids 中已被其它组占用的 [{store_id, store_name, group_id, group_name}]"""
    if not store_ids:
        return []
    sql = """
        SELECT m.store_id, s.store_name, m.group_id, g.name AS group_name
        FROM biz_store_report_group_members m
        JOIN biz_store_report_groups g ON g.id = m.group_id
        LEFT JOIN biz_stores s ON s.id = m.store_id
        WHERE m.store_id = ANY(:ids)
    """
    params = {"ids": list(store_ids)}
    if exclude_group_id is not None:
        sql += " AND m.group_id <> :gid"
        params["gid"] = exclude_group_id
    r = await db.execute(text(sql), params)
    return [dict(row) for row in r.mappings()]


@router.get("")
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """列出所有店铺组及其成员"""
    groups = await db.execute(text("""
        SELECT id, name, remark, is_active, parent_group_id, created_at, updated_at
        FROM biz_store_report_groups
        ORDER BY name
    """))
    groups = [dict(g) for g in groups.mappings()]
    members = await db.execute(text("""
        SELECT m.group_id, m.store_id, s.store_name,
               COALESCE(bp.name, '') AS platform
        FROM biz_store_report_group_members m
        LEFT JOIN biz_stores s ON s.id = m.store_id
        LEFT JOIN biz_platforms bp ON bp.id = s.platform_id
        ORDER BY s.store_name
    """))
    by_group: dict = {}
    for m in members.mappings():
        by_group.setdefault(m["group_id"], []).append(
            {"store_id": m["store_id"], "store_name": m["store_name"], "platform": m["platform"]}
        )
    for g in groups:
        g["members"] = by_group.get(g["id"], [])
    return groups


@router.post("")
async def create_group(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """新建店铺组。body: {name, remark?, store_ids:[int]}"""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="组名必填")
    store_ids = [int(x) for x in (body.get("store_ids") or [])]

    parent_group_id = body.get("parent_group_id")
    await _validate_parent(db, None, parent_group_id)
    occupied = await _check_occupied(db, store_ids, exclude_group_id=None)
    if occupied:
        names = "、".join(o["store_name"] or str(o["store_id"]) for o in occupied)
        raise HTTPException(status_code=409, detail=f"以下店铺已属其它组：{names}")

    try:
        r = await db.execute(text("""
            INSERT INTO biz_store_report_groups (name, remark, parent_group_id, created_by)
            VALUES (:name, :remark, :pid, :uid) RETURNING id
        """), {"name": name, "remark": body.get("remark"),
              "pid": int(parent_group_id) if parent_group_id is not None else None,
              "uid": current_user.id})
        gid = r.scalar_one()
        for sid in store_ids:
            await db.execute(text("""
                INSERT INTO biz_store_report_group_members (group_id, store_id)
                VALUES (:gid, :sid)
            """), {"gid": gid, "sid": sid})
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        msg = "组名重复" if "uq_srg_name" in str(e.orig) else "店铺已属其它组（并发冲突）"
        raise HTTPException(status_code=409, detail=msg)
    return {"ok": True, "id": gid}


@router.put("/{group_id}")
async def update_group(
    group_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """更新组属性；若传 store_ids 则全量替换成员。
    顺序：先 delete 本组成员 → 跨组占用校验(排除本组) → insert，整段一个事务。"""
    exists = await db.execute(text("SELECT 1 FROM biz_store_report_groups WHERE id=:id"), {"id": group_id})
    if not exists.first():
        raise HTTPException(status_code=404, detail="店铺组不存在")

    sets, params = [], {"id": group_id}
    if "name" in body:
        nm = (body.get("name") or "").strip()
        if not nm:
            raise HTTPException(status_code=422, detail="组名不能为空")
        sets.append("name=:name"); params["name"] = nm
    if "remark" in body:
        sets.append("remark=:remark"); params["remark"] = body.get("remark")
    if "is_active" in body:
        sets.append("is_active=:ia"); params["ia"] = bool(body.get("is_active"))
    if "parent_group_id" in body:
        pid = body.get("parent_group_id")
        await _validate_parent(db, group_id, pid)
        sets.append("parent_group_id=:pid"); params["pid"] = int(pid) if pid is not None else None

    try:
        if sets:
            sets.append("updated_at=now()")
            await db.execute(text(f"UPDATE biz_store_report_groups SET {', '.join(sets)} WHERE id=:id"), params)

        if "store_ids" in body:
            store_ids = [int(x) for x in (body.get("store_ids") or [])]
            await db.execute(text("DELETE FROM biz_store_report_group_members WHERE group_id=:gid"), {"gid": group_id})
            occupied = await _check_occupied(db, store_ids, exclude_group_id=group_id)
            if occupied:
                await db.rollback()
                names = "、".join(o["store_name"] or str(o["store_id"]) for o in occupied)
                raise HTTPException(status_code=409, detail=f"以下店铺已属其它组：{names}")
            for sid in store_ids:
                await db.execute(text("""
                    INSERT INTO biz_store_report_group_members (group_id, store_id)
                    VALUES (:gid, :sid)
                """), {"gid": group_id, "sid": sid})
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        msg = "组名重复" if "uq_srg_name" in str(e.orig) else "店铺已属其它组（并发冲突）"
        raise HTTPException(status_code=409, detail=msg)
    return {"ok": True}


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _ = Depends(get_current_user),
):
    """删除店铺组（成员 CASCADE）"""
    await db.execute(text("DELETE FROM biz_store_report_groups WHERE id=:id"), {"id": group_id})
    await db.commit()
    return {"ok": True}
