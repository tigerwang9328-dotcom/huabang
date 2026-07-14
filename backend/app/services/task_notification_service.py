"""Per-recipient durable outbox for task assignment and overdue notifications."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from app.core.database import AsyncSessionLocal
from app.models.app import AppActionTask, AppTaskNotificationOutbox
from app.services.dingtalk import DingtalkService
from app.services.task_workflow_service import normalize_assignee_roles

logger = logging.getLogger("task.notification")

MAX_NOTIFICATION_ATTEMPTS = 5
BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_today(now: datetime | None = None) -> date:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(BEIJING).date()


class TaskNotificationService:
    async def enqueue_assignment(self, db, task: AppActionTask) -> str:
        event_key = f"task:{task.id}:assignment:v{int(task.workflow_version or 0)}"
        return await self._enqueue(db, task, kind="assignment", event_key=event_key)

    async def enqueue_overdue(self, db, task: AppActionTask, reminder_date: date) -> str:
        event_key = f"task:{task.id}:overdue:{reminder_date.isoformat()}"
        return await self._enqueue(db, task, kind="overdue", event_key=event_key)

    async def _enqueue(self, db, task: AppActionTask, *, kind: str, event_key: str) -> str:
        recipients = await self._recipient_ids(db, task)
        for recipient in recipients:
            await db.execute(text("""
                INSERT INTO app.app_task_notification_outbox(
                    task_id, event_key, notification_kind, recipient_user_id, status
                ) VALUES (:task_id, :event_key, :kind, :recipient, 'queued')
                ON CONFLICT (event_key, recipient_user_id) DO NOTHING
            """), {
                "task_id": task.id,
                "event_key": event_key,
                "kind": kind,
                "recipient": recipient,
            })

        task.notification_event_key = event_key
        task.notification_kind = kind
        task.notification_status = "queued" if recipients else "skipped"
        task.notification_pending_recipients = recipients or None
        task.notification_attempt_count = 0
        task.notification_error = None if recipients else "未找到已绑定钉钉的责任人"
        task.notification_updated_at = datetime.now(timezone.utc)
        if recipients:
            await self._refresh_task_summary(db, task.id, event_key)
        return event_key

    async def notify_assignment(self, task_id: int, *, force_retry: bool = False) -> dict[str, Any]:
        if force_retry:
            return await self.retry(task_id, actor_id=None)
        event_key = await self._ensure_event(task_id, kind="assignment")
        if event_key is None:
            return {"success": False, "reason": "task_not_found"}
        return await self._process_event(event_key)

    async def notify_overdue(self, task_id: int, *, force_retry: bool = False) -> dict[str, Any]:
        if force_retry:
            return await self.retry(task_id, actor_id=None)
        event_key = await self._ensure_event(task_id, kind="overdue")
        if event_key is None:
            return {"success": False, "reason": "task_not_found"}
        return await self._process_event(event_key)

    async def _ensure_event(self, task_id: int, *, kind: str) -> str | None:
        async with AsyncSessionLocal() as db:
            task = await db.scalar(select(AppActionTask).where(AppActionTask.id == task_id))
            if task is None:
                return None
            if task.notification_event_key and task.notification_kind == kind:
                return task.notification_event_key
            if kind == "overdue":
                event_key = await self.enqueue_overdue(db, task, beijing_today())
            else:
                event_key = await self.enqueue_assignment(db, task)
            await db.commit()
            return event_key

    async def process_pending(self, *, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Drain retryable rows and quarantine stale in-flight deliveries as uncertain."""
        async with AsyncSessionLocal() as db:
            stale = (await db.execute(text("""
                UPDATE app.app_task_notification_outbox
                SET status='uncertain',
                    last_error='发送进程中断，钉钉是否接收未知；需人工确认后重试',
                    updated_at=now()
                WHERE status='sending'
                  AND claimed_at<now()-interval '30 minutes'
                  AND (CAST(:kind AS varchar) IS NULL OR notification_kind=CAST(:kind AS varchar))
                RETURNING task_id, event_key
            """), {"kind": kind})).all()
            for task_id, event_key in set(stale):
                await self._refresh_task_summary(db, int(task_id), event_key)
            rows = (await db.execute(text("""
                SELECT id
                FROM app.app_task_notification_outbox
                WHERE (CAST(:kind AS varchar) IS NULL OR notification_kind=CAST(:kind AS varchar))
                  AND attempt_count < :max_attempts + manual_retry_count
                  AND (next_attempt_at IS NULL OR next_attempt_at<=now())
                  AND (
                      status='queued'
                      OR (status='failed' AND updated_at<now()-interval '5 minutes')
                  )
                ORDER BY updated_at, id
                LIMIT :limit
            """), {
                "kind": kind,
                "limit": limit,
                "max_attempts": MAX_NOTIFICATION_ATTEMPTS,
            })).scalars().all()
            await db.commit()

        return [await self._deliver_outbox(int(outbox_id)) for outbox_id in rows]

    async def retry(self, task_id: int, *, actor_id: int | None) -> dict[str, Any]:
        """Explicitly retry terminal/uncertain recipients and audit the operator."""
        async with AsyncSessionLocal() as db:
            task = await db.scalar(
                select(AppActionTask).where(AppActionTask.id == task_id).with_for_update()
            )
            if task is None:
                return {"success": False, "reason": "task_not_found"}
            event_key = task.notification_event_key
            if not event_key:
                event_key = await self.enqueue_assignment(db, task)

            await db.execute(text("""
                UPDATE app.app_task_notification_outbox
                SET status='uncertain',
                    last_error='发送超时，结果未知；等待人工确认',
                    updated_at=now()
                WHERE event_key=:event_key AND status='sending'
                  AND claimed_at<now()-interval '30 minutes'
            """), {"event_key": event_key})
            active = int((await db.scalar(select(func.count()).select_from(
                select(AppTaskNotificationOutbox.id).where(
                    AppTaskNotificationOutbox.event_key == event_key,
                    AppTaskNotificationOutbox.status == "sending",
                ).subquery()
            ))) or 0)
            if active:
                await db.rollback()
                return {
                    "success": False,
                    "in_progress": True,
                    "status": "sending",
                    "reason": "notification_in_progress",
                }

            updated = (await db.execute(text("""
                UPDATE app.app_task_notification_outbox
                SET status='queued',
                    manual_retry_count=manual_retry_count+1,
                    last_error=NULL,
                    claimed_at=NULL,
                    next_attempt_at=NULL,
                    updated_at=now()
                WHERE event_key=:event_key
                  AND status IN ('queued','failed','skipped','uncertain')
                RETURNING id
            """), {
                "event_key": event_key,
                "max_attempts": MAX_NOTIFICATION_ATTEMPTS,
            })).scalars().all()

            if not updated and task.notification_status == "skipped":
                kind = task.notification_kind or "assignment"
                await self._enqueue(db, task, kind=kind, event_key=event_key)
                updated = (await db.execute(select(AppTaskNotificationOutbox.id).where(
                    AppTaskNotificationOutbox.event_key == event_key,
                    AppTaskNotificationOutbox.status == "queued",
                ))).scalars().all()
            if not updated:
                await db.rollback()
                return await self._event_result(event_key)

            task.notification_manual_retry_count = int(task.notification_manual_retry_count or 0) + 1
            task.notification_last_retry_by = actor_id
            task.notification_last_retry_at = datetime.now(timezone.utc)
            task.notification_status = "queued"
            task.notification_error = None
            task.notification_updated_at = datetime.now(timezone.utc)
            await db.commit()
        return await self._process_event(event_key)

    async def _process_event(self, event_key: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(AppTaskNotificationOutbox.id).where(
                AppTaskNotificationOutbox.event_key == event_key,
                AppTaskNotificationOutbox.status == "queued",
            ).order_by(AppTaskNotificationOutbox.id))).scalars().all()
        for outbox_id in rows:
            await self._deliver_outbox(int(outbox_id))
        return await self._event_result(event_key)

    async def _deliver_outbox(self, outbox_id: int) -> dict[str, Any]:
        claim = await self._claim(outbox_id)
        if claim is None:
            return {"success": False, "in_progress": True, "reason": "not_claimed"}
        claim_generation = int(claim["claim_generation"])
        try:
            async with AsyncSessionLocal() as db:
                outbox = await db.scalar(select(AppTaskNotificationOutbox).where(
                    AppTaskNotificationOutbox.id == outbox_id
                ))
                task = await db.scalar(select(AppActionTask).where(AppActionTask.id == claim["task_id"]))
                if outbox is None or task is None:
                    return {"success": False, "reason": "task_not_found"}
                if not await self._claim_is_current(db, outbox_id, claim_generation):
                    return {
                        "success": False,
                        "superseded": True,
                        "reason": "notification_claim_replaced",
                    }

                due = str(task.due_date) if task.due_date else "未设置"
                if outbox.notification_kind == "overdue":
                    title = f"【任务逾期】{task.title}"
                    content = (
                        f"## 任务已逾期\n\n- 任务：{task.title}\n- 截止：{due}\n"
                        f"- 要求：{task.feedback_requirement or '请尽快反馈处理结果'}\n"
                    )
                    push_type = "task_overdue"
                else:
                    title = f"【任务派发】{task.title}"
                    content = (
                        f"## 新任务待处理\n\n- 任务：{task.title}\n- 截止：{due}\n"
                        f"- 要求：{task.feedback_requirement or '请按要求提交处理结果'}\n"
                    )
                    push_type = "task_assignment"

                result = await DingtalkService(db).send_work_notification(
                    user_id_list=[outbox.recipient_user_id],
                    title=title,
                    content=content,
                    push_type=push_type,
                    template_code=push_type,
                    notification_key=f"{outbox.event_key}:{outbox.recipient_user_id}",
                )
                recipient_result = (result.get("results") or [{}])[0]
                if result.get("deferred") or recipient_result.get("deferred"):
                    finalized = await self._defer_until_budget_reset(
                        db,
                        outbox_id,
                        claim_generation,
                        error=str(recipient_result.get("error") or "钉钉预算已用尽，延迟到次日"),
                    )
                    await self._refresh_task_summary(db, task.id, outbox.event_key)
                    await db.commit()
                    return result if finalized else {
                        "success": False,
                        "superseded": True,
                        "reason": "notification_claim_replaced",
                    }
                if result.get("success"):
                    status = "success"
                    error = None
                elif result.get("uncertain") or recipient_result.get("uncertain"):
                    status = "uncertain"
                    error = str(recipient_result.get("error") or "钉钉是否接收未知，需人工确认")
                elif result.get("skipped"):
                    status = "skipped"
                    error = str(result.get("reason") or "通知已跳过")
                else:
                    status = "failed"
                    error = str(result.get("reason") or result.get("results") or "通知失败")
                finalized = await self._finalize(
                    db,
                    outbox_id,
                    claim_generation,
                    status=status,
                    error=error,
                )
                await self._refresh_task_summary(db, task.id, outbox.event_key)
                await db.commit()
                if not finalized:
                    return {
                        "success": False,
                        "superseded": True,
                        "reason": "notification_claim_replaced",
                    }
                return result
        except Exception as exc:
            logger.exception("Task notification failed outbox_id=%s", outbox_id)
            await self._finalize_failure(outbox_id, claim_generation, str(exc))
            return {"success": False, "reason": "notification_failed", "error": str(exc)}

    async def _claim(self, outbox_id: int) -> dict[str, Any] | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                WITH candidate AS (
                    SELECT id
                    FROM app.app_task_notification_outbox
                    WHERE id=:outbox_id
                      AND attempt_count < :max_attempts + manual_retry_count
                      AND (next_attempt_at IS NULL OR next_attempt_at<=now())
                      AND (
                          status='queued'
                          OR (status='failed' AND updated_at<now()-interval '5 minutes')
                      )
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE app.app_task_notification_outbox outbox
                SET status='sending', attempt_count=attempt_count+1,
                    claim_generation=claim_generation+1,
                    claimed_at=now(),
                    updated_at=now(), last_error=NULL
                FROM candidate
                WHERE outbox.id=candidate.id
                RETURNING outbox.task_id, outbox.event_key,
                          outbox.recipient_user_id, outbox.attempt_count,
                          outbox.claim_generation
            """), {
                "outbox_id": outbox_id,
                "max_attempts": MAX_NOTIFICATION_ATTEMPTS,
            })).first()
            await db.commit()
        if row is None:
            return None
        return {
            "task_id": int(row[0]),
            "event_key": row[1],
            "recipient_user_id": row[2],
            "attempt_count": int(row[3]),
            "claim_generation": int(row[4]),
        }

    async def _claim_is_current(self, db, outbox_id: int, claim_generation: int) -> bool:
        current = await db.scalar(select(AppTaskNotificationOutbox.id).where(
            AppTaskNotificationOutbox.id == outbox_id,
            AppTaskNotificationOutbox.status == "sending",
            AppTaskNotificationOutbox.claim_generation == claim_generation,
        ))
        return current is not None

    async def _defer_until_budget_reset(
        self,
        db,
        outbox_id: int,
        claim_generation: int,
        *,
        error: str,
    ) -> bool:
        next_day = datetime.combine(
            beijing_today() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=BEIJING,
        ).astimezone(timezone.utc)
        row = (await db.execute(text("""
            UPDATE app.app_task_notification_outbox
            SET status='queued',
                attempt_count=GREATEST(attempt_count-1,0),
                last_error=:error,
                claimed_at=NULL,
                next_attempt_at=:next_attempt_at,
                updated_at=now()
            WHERE id=:outbox_id
              AND status='sending'
              AND claim_generation=:claim_generation
            RETURNING id
        """), {
            "outbox_id": outbox_id,
            "claim_generation": claim_generation,
            "error": error[:500],
            "next_attempt_at": next_day,
        })).first()
        return row is not None

    async def _finalize(self, db, outbox_id: int, claim_generation: int, *, status: str, error: str | None) -> bool:
        row = (await db.execute(text("""
            UPDATE app.app_task_notification_outbox
            SET status=CAST(:status AS varchar),
                last_error=:error,
                delivered_at=CASE WHEN CAST(:status AS varchar)='success' THEN now() ELSE delivered_at END,
                next_attempt_at=NULL,
                updated_at=now()
            WHERE id=:outbox_id AND status='sending' AND claim_generation=:claim_generation
            RETURNING id
        """), {
            "outbox_id": outbox_id,
            "claim_generation": claim_generation,
            "status": status,
            "error": (error or "")[:500] or None,
        })).first()
        return row is not None

    async def _finalize_failure(self, outbox_id: int, claim_generation: int, error: str) -> None:
        try:
            async with AsyncSessionLocal() as db:
                outbox = await db.scalar(select(AppTaskNotificationOutbox).where(
                    AppTaskNotificationOutbox.id == outbox_id
                ))
                if outbox is None:
                    return
                await self._finalize(db, outbox_id, claim_generation, status="failed", error=error)
                await self._refresh_task_summary(db, outbox.task_id, outbox.event_key)
                await db.commit()
        except Exception:
            logger.exception("Unable to persist task notification failure outbox_id=%s", outbox_id)

    async def _refresh_task_summary(self, db, task_id: int, event_key: str) -> None:
        latest = (await db.execute(text("""
            SELECT event_key, notification_kind
            FROM app.app_task_notification_outbox
            WHERE task_id=:task_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """), {"task_id": task_id})).first()
        if latest is None or latest[0] != event_key:
            return
        row = (await db.execute(text("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE status='success') AS success_count,
                   count(*) FILTER (WHERE status='sending') AS sending_count,
                   count(*) FILTER (WHERE status='queued') AS queued_count,
                   count(*) FILTER (WHERE status='uncertain') AS uncertain_count,
                   count(*) FILTER (WHERE status='failed') AS failed_count,
                   count(*) FILTER (WHERE status='skipped') AS skipped_count,
                   COALESCE(max(attempt_count),0) AS attempts,
                   array_agg(recipient_user_id ORDER BY recipient_user_id)
                       FILTER (WHERE status<>'success') AS pending,
                   string_agg(last_error, '; ' ORDER BY id)
                       FILTER (WHERE last_error IS NOT NULL) AS errors
            FROM app.app_task_notification_outbox
            WHERE event_key=:event_key
        """), {"event_key": event_key})).first()
        if row is None or int(row[0]) == 0:
            return
        total, succeeded, sending, queued, uncertain, failed, skipped = map(int, row[:7])
        if uncertain:
            status = "uncertain"
        elif sending:
            status = "sending"
        elif queued:
            status = "queued"
        elif succeeded == total:
            status = "success"
        elif succeeded:
            status = "partial"
        elif failed:
            status = "failed"
        elif skipped:
            status = "skipped"
        else:
            status = "failed"
        await db.execute(text("""
            UPDATE app.app_action_task
            SET notification_event_key=:event_key,
                notification_kind=CAST(:kind AS varchar),
                notification_status=CAST(:status AS varchar),
                notification_pending_recipients=CAST(:pending AS jsonb),
                notification_attempt_count=:attempts,
                notification_error=:errors,
                notification_updated_at=now(),
                dingtalk_notified_at=CASE WHEN CAST(:status AS varchar)='success' THEN now() ELSE dingtalk_notified_at END,
                dingtalk_reminder_count=CASE
                    WHEN CAST(:status AS varchar)='success'
                         AND CAST(:kind AS varchar)='overdue'
                         AND notification_status IS DISTINCT FROM 'success'
                    THEN COALESCE(dingtalk_reminder_count,0)+1
                    ELSE dingtalk_reminder_count
                END,
                updated_at=now()
            WHERE id=:task_id
              AND (notification_event_key IS NULL OR notification_event_key=:event_key)
        """), {
            "task_id": task_id,
            "event_key": event_key,
            "kind": latest[1],
            "status": status,
            "pending": __import__("json").dumps(row[8] or None),
            "attempts": int(row[7]),
            "errors": (row[9] or "")[:500] or None,
        })

    async def _event_result(self, event_key: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(
                AppTaskNotificationOutbox.status,
                AppTaskNotificationOutbox.recipient_user_id,
                AppTaskNotificationOutbox.last_error,
            ).where(AppTaskNotificationOutbox.event_key == event_key))).all()
        if not rows:
            return {"success": False, "skipped": True, "reason": "no_recipient"}
        failed = [row[1] for row in rows if row[0] != "success"]
        success_count = len(rows) - len(failed)
        return {
            "success": not failed,
            "partial": 0 < success_count < len(rows),
            "total": len(rows),
            "success_count": success_count,
            "failed_recipient_ids": failed,
            "status": "success" if not failed else ("partial" if success_count else rows[0][0]),
            "results": [
                {"user_id": row[1], "success": row[0] == "success", "status": row[0], "error": row[2]}
                for row in rows
            ],
        }

    async def _recipient_ids(self, db, task: AppActionTask) -> list[str]:
        if task.assignee_id is not None:
            rows = (await db.execute(text("""
                SELECT DISTINCT COALESCE(
                    (
                        SELECT active_bind.dingtalk_user_id
                        FROM sys.sys_dingtalk_bind active_bind
                        WHERE active_bind.user_id=u.id
                          AND active_bind.is_active=true
                          AND COALESCE(active_bind.push_enabled,true)=true
                        ORDER BY active_bind.id DESC LIMIT 1
                    ),
                    CASE WHEN NOT EXISTS (
                        SELECT 1 FROM sys.sys_dingtalk_bind any_bind WHERE any_bind.user_id=u.id
                    ) THEN NULLIF(u.dingtalk_user_id,'') END
                )
                FROM sys.sys_user u
                WHERE u.id=:user_id AND u.status=1 AND u.is_deleted=false
            """), {"user_id": task.assignee_id})).scalars().all()
            return [value for value in rows if value]

        roles = sorted(normalize_assignee_roles(task.assignee_role))
        if not roles:
            return []
        rows = (await db.execute(text("""
            SELECT DISTINCT COALESCE(
                (
                    SELECT active_bind.dingtalk_user_id
                    FROM sys.sys_dingtalk_bind active_bind
                    WHERE active_bind.user_id=u.id
                      AND active_bind.is_active=true
                      AND COALESCE(active_bind.push_enabled,true)=true
                    ORDER BY active_bind.id DESC LIMIT 1
                ),
                CASE WHEN NOT EXISTS (
                    SELECT 1 FROM sys.sys_dingtalk_bind any_bind WHERE any_bind.user_id=u.id
                ) THEN NULLIF(u.dingtalk_user_id,'') END
            )
            FROM sys.sys_user u
            JOIN sys.sys_user_role ur ON ur.user_id=u.id
            JOIN sys.sys_role r ON r.id=ur.role_id AND r.code=ANY(:roles) AND r.status=1
            LEFT JOIN sys.sys_user creator ON creator.id=:creator_id
            WHERE u.status=1 AND u.is_deleted=false
              AND (
                  r.data_scope IN ('all','company')
                  OR (r.data_scope='dept' AND creator.dept_id IS NOT NULL AND u.dept_id=creator.dept_id)
                  OR (
                      COALESCE(r.data_scope,'self') IN ('store','self')
                      AND COALESCE(CAST(:store_code AS varchar), creator.store_code) IS NOT NULL
                      AND (
                          u.store_code=COALESCE(CAST(:store_code AS varchar), creator.store_code)
                          OR EXISTS (
                              SELECT 1 FROM sys.sys_user_store us
                              WHERE us.user_id=u.id
                                AND us.store_code=COALESCE(CAST(:store_code AS varchar), creator.store_code)
                          )
                      )
                  )
              )
            ORDER BY 1
        """), {
            "roles": roles,
            "creator_id": task.creator_id,
            "store_code": task.related_store_code,
        })).scalars().all()
        return [value for value in rows if value]
