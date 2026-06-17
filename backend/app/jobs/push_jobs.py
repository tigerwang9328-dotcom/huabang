"""push_jobs - 钉钉定时推送任务（补货/逾期/诊断）"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


async def run_daily_sync():
    """1:00 数据同步+ETL"""
    stat_date = (date.today() - timedelta(days=1)).isoformat()
    logger.info(f"[定时] 每日ETL开始: {stat_date}")
    try:
        from app.services.etl.pipeline import ETLPipeline
        from app.core.database import AsyncSessionLocal
        pipeline = ETLPipeline()
        async with AsyncSessionLocal() as db:
            result = await pipeline.run_full(stat_date, db)
            logger.info(f"[定时] ETL完成: {result}")
    except Exception as e:
        logger.error(f"[定时] ETL失败: {e}", exc_info=True)


async def run_member_visit_push():
    """10:00 会员回访名单推送（TODO: 待接入会员回访规则）"""
    logger.info("[定时] 会员回访名单推送（暂未实现，跳过）")


async def run_replenishment_push():
    """14:00 补货/调拨提醒"""
    stat_date = (date.today() - timedelta(days=1)).isoformat()
    logger.info(f"[定时] 补货提醒: {stat_date}")
    try:
        from sqlalchemy import text
        from datetime import date as ddate
        from app.services.dingtalk import DingtalkService
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            d = ddate.fromisoformat(stat_date)
            r = await db.execute(text("""
                SELECT store_code, product_code, current_quantity, sellable_days, urgency
                FROM dm.dm_replenishment_advice
                WHERE advice_date = :d AND urgency = 'urgent'
                ORDER BY sellable_days LIMIT 10
            """), {"d": d})
            rows = r.fetchall()

            if not rows:
                logger.info("[定时] 无紧急补货需求")
                return

            lines = [f"## 华邦 {stat_date} 补货提醒", "", "**以下商品库存告急，请安排补货：**", ""]
            for row in rows:
                lines.append(f"- 门店 **{row[0]}** | 商品 {row[1]} | 现库存{row[2]}件 | 预计{row[3]}天售罄")

            content = "\n".join(lines) + f"\n\n---\n*请及时处理，避免断货影响销售*"

            dt_svc = DingtalkService(db)
            user_ids = await dt_svc.get_push_user_ids()
            if user_ids:
                result = await dt_svc.send_work_notification(
                    user_id_list=user_ids,
                    title=f"【补货提醒】{len(rows)}个SKU库存告急",
                    content=content,
                    push_type="replenishment",
                    template_code="replenishment",
                )
                await db.commit()
                logger.info(f"[定时] 补货推送: {result}")
    except Exception as e:
        logger.error(f"[定时] 补货提醒失败: {e}", exc_info=True)


async def run_overdue_reminder():
    """18:00 任务逾期提醒"""
    logger.info("[定时] 任务逾期提醒开始")
    try:
        from sqlalchemy import text
        from app.services.dingtalk import DingtalkService
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT title, assignee_name, assignee_id
                FROM app.app_action_task
                WHERE status = 'overdue' AND is_deleted = FALSE
                LIMIT 10
            """))
            rows = r.fetchall()

            if not rows:
                logger.info("[定时] 无逾期任务")
                return

            lines = ["## 任务逾期提醒", "", f"当前共 **{len(rows)}** 个任务已逾期：", ""]
            for row in rows:
                lines.append(f"- {row[0]}（{row[1] or '未分配'}）")

            content = "\n".join(lines) + "\n\n请及时处理逾期任务！"

            dt_svc = DingtalkService(db)
            user_ids = await dt_svc.get_push_user_ids()
            if user_ids:
                result = await dt_svc.send_work_notification(
                    user_id_list=user_ids,
                    title=f"【逾期提醒】{len(rows)}个任务待处理",
                    content=content,
                    push_type="overdue_reminder",
                    template_code="overdue_reminder",
                )
                await db.commit()
                logger.info(f"[定时] 逾期提醒推送: {result}")
    except Exception as e:
        logger.error(f"[定时] 逾期提醒失败: {e}", exc_info=True)


async def run_evening_diagnosis():
    """21:30 晚间门店诊断（规则引擎扫描 + 推送异常结果）"""
    stat_date = (date.today() - timedelta(days=1)).isoformat()
    logger.info(f"[定时] 晚间诊断: {stat_date}")
    try:
        from app.services.rule_engine import RuleEngine
        from app.services.dingtalk import DingtalkService
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            engine = RuleEngine()
            result = await engine.run_all(stat_date, db)
            triggered = [r for r in result["results"] if r["triggered"]]
            critical = [r for r in triggered if r["severity"] in ("critical", "risk")]

            if not critical:
                logger.info(f"[定时] 晚间诊断正常，规则触发数: {result['triggered_count']}")
                return

            lines = ["## 晚间经营诊断报告", "", f"**触发{result['triggered_count']}条规则，其中高危{len(critical)}条：**", ""]
            for r in critical[:5]:
                lines.append(f"- 【{r['severity'].upper()}】{r['title']}")
            if result['triggered_count'] > 5:
                lines.append(f"- ...还有 {result['triggered_count']-5} 条预警")

            content = "\n".join(lines) + "\n\n请及时查看华邦AI中台详情"

            dt_svc = DingtalkService(db)
            user_ids = await dt_svc.get_push_user_ids()
            if user_ids:
                await dt_svc.send_work_notification(
                    user_id_list=user_ids,
                    title=f"【晚间诊断】发现{len(critical)}条高危预警",
                    content=content,
                    push_type="evening_diagnosis",
                    template_code="evening_diagnosis",
                )
                await db.commit()
                logger.info(f"[定时] 晚间诊断推送完成")
    except Exception as e:
        logger.error(f"[定时] 晚间诊断失败: {e}", exc_info=True)
