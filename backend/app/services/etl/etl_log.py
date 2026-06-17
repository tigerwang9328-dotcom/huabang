"""
ETL日志工具：使用psycopg2同步写入 log.log_etl_run
"""
import os
import traceback
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras


def _get_dsn() -> str:
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME", "huabang")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


class ETLLogger:
    """
    同步写 log.log_etl_run。
    不使用 async，避免与 asyncio event loop 耦合带来的复杂度。
    """

    def __init__(self):
        self._dsn = _get_dsn()

    def _connect(self):
        return psycopg2.connect(self._dsn)

    def start_task(self, task_name: str, stat_date: str) -> int:
        """
        插入一条 running 状态的日志，返回 run_id。
        """
        sql = """
            INSERT INTO log.log_etl_run
                (task_name, started_at, status, stat_date)
            VALUES
                (%s, %s, 'running', %s)
            RETURNING id
        """
        now = datetime.now(timezone.utc)
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (task_name, now, stat_date))
                    run_id = cur.fetchone()[0]
                conn.commit()
                return run_id
            finally:
                conn.close()
        except Exception as exc:
            # 日志写失败不应阻断业务，返回 -1
            print(f"[ETLLogger] start_task 写入失败: {exc}")
            return -1

    def finish_task(
        self,
        run_id: int,
        output_rows: int = 0,
        input_rows: int = 0,
    ) -> None:
        """
        更新为 success 状态。
        """
        if run_id < 0:
            return
        sql = """
            UPDATE log.log_etl_run
            SET finished_at = %s,
                status      = 'success',
                output_rows = %s,
                input_rows  = %s
            WHERE id = %s
        """
        now = datetime.now(timezone.utc)
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (now, output_rows, input_rows, run_id))
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            print(f"[ETLLogger] finish_task 写入失败: {exc}")

    def fail_task(
        self,
        run_id: int,
        error_msg: str,
        is_retryable: bool = True,
    ) -> None:
        """
        更新为 failed 状态。
        """
        if run_id < 0:
            return
        # 截断超长 error_msg
        error_msg = (error_msg or "")[:2000]
        sql = """
            UPDATE log.log_etl_run
            SET finished_at   = %s,
                status        = 'failed',
                error_msg     = %s,
                is_retryable  = %s
            WHERE id = %s
        """
        now = datetime.now(timezone.utc)
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (now, error_msg, is_retryable, run_id))
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            print(f"[ETLLogger] fail_task 写入失败: {exc}")

    def log_exception(self, run_id: int, exc: Exception) -> None:
        """
        便捷方法：将异常格式化后写入 fail_task。
        """
        tb = traceback.format_exc()
        self.fail_task(run_id, f"{type(exc).__name__}: {exc}\n{tb}")
