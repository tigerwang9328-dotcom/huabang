"""Isolated v3.1 color-analysis Task 0 upload-contract proof.

It is intentionally separate from the legacy v3.2 outfit proof and is not
registered with production routers, models, migrations, or services.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import sqlite3
from contextlib import asynccontextmanager
from threading import RLock
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_curve(raw_response: dict[str, Any]) -> list[dict[str, float]]:
    """Convert the Task-0 whitelist's percent-or-ratio points to 0..1."""
    points = raw_response.get("response_data", {}).get("analysis_trend", {}).get("current_item", [])
    normalized: list[dict[str, float]] = []
    for point in points:
        value = float(point["value"])
        if value > 1:
            value /= 100
        if not 0 <= value <= 1:
            raise HTTPException(status_code=400, detail="invalid_curve_value")
        normalized.append({"second": int(point["second"]), "value": value})
    if not normalized:
        raise HTTPException(status_code=400, detail="empty_curve")
    return normalized


class V31ContractStore:
    """Minimal relational contract surface; not a production data model."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE accounts (
                id TEXT PRIMARY KEY,
                expected_creator_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE upload_tokens (
                token TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id)
            );
            CREATE TABLE garment_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                style_code TEXT NOT NULL,
                UNIQUE(account_id, style_code)
            );
            CREATE TABLE garment_colors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                style_id INTEGER NOT NULL REFERENCES garment_styles(id),
                color_code TEXT NOT NULL,
                UNIQUE(style_id, color_code)
            );
            CREATE TABLE collection_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                client_batch_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                observed_creator_id TEXT NOT NULL,
                part_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                batch_hash TEXT,
                UNIQUE(account_id, client_batch_id)
            );
            CREATE TABLE collection_batch_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL REFERENCES collection_batches(id),
                part_number INTEGER NOT NULL,
                part_hash TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                UNIQUE(batch_id, part_number),
                UNIQUE(batch_id, part_hash)
            );
            CREATE TABLE video_analysis_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                video_id TEXT NOT NULL,
                analysis_type INTEGER NOT NULL,
                source_snapshot_hash TEXT NOT NULL,
                raw_response_json TEXT,
                normalized_curve_json TEXT,
                UNIQUE(account_id, video_id, analysis_type, source_snapshot_hash)
            );
            CREATE TABLE collection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                batch_id INTEGER NOT NULL REFERENCES collection_batches(id),
                part_id INTEGER NOT NULL REFERENCES collection_batch_parts(id),
                snapshot_id INTEGER REFERENCES video_analysis_snapshots(id),
                raw_record_hash TEXT,
                item_status TEXT NOT NULL,
                UNIQUE(part_id, raw_record_hash)
            );
            """
        )
        self.connection.executemany(
            "INSERT INTO accounts(id, expected_creator_id) VALUES (?, ?)",
            [("color-account-a", "creator-a"), ("color-account-b", "creator-b")],
        )
        self.connection.executemany(
            "INSERT INTO upload_tokens(token, account_id) VALUES (?, ?)",
            [("color-token-a", "color-account-a"), ("color-token-b", "color-account-b")],
        )

    def close(self) -> None:
        self.connection.close()

    def account_for_token(self, token: str) -> sqlite3.Row:
        row = self.connection.execute(
            """
            SELECT accounts.id, accounts.expected_creator_id
            FROM upload_tokens JOIN accounts ON accounts.id = upload_tokens.account_id
            WHERE upload_tokens.token = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="invalid_upload_token")
        return row

    def create_style(self, account_id: str, style_code: str) -> dict[str, Any]:
        with self._lock, self.connection:
            cursor = self.connection.execute(
                "INSERT INTO garment_styles(account_id, style_code) VALUES (?, ?)",
                (account_id, style_code),
            )
        return {"id": int(cursor.lastrowid), "style_code": style_code}

    def create_color(
        self, account_id: str, style_id: int, color_code: str
    ) -> dict[str, Any]:
        with self._lock, self.connection:
            style = self.connection.execute(
                "SELECT account_id FROM garment_styles WHERE id = ?", (style_id,)
            ).fetchone()
            if style is None or style["account_id"] != account_id:
                raise HTTPException(status_code=409, detail="style_account_mismatch")
            cursor = self.connection.execute(
                """
                INSERT INTO garment_colors(account_id, style_id, color_code)
                VALUES (?, ?, ?)
                """,
                (account_id, style_id, color_code),
            )
        return {"id": int(cursor.lastrowid), "color_code": color_code}

    def _assert_owned_references(
        self, account_id: str, record: dict[str, Any]
    ) -> None:
        style_id = record.get("style_id")
        color_id = record.get("color_id")
        if style_id is not None:
            style = self.connection.execute(
                "SELECT account_id FROM garment_styles WHERE id = ?", (style_id,)
            ).fetchone()
            if style is None or style["account_id"] != account_id:
                raise HTTPException(status_code=409, detail="style_account_mismatch")
        if color_id is not None:
            color = self.connection.execute(
                "SELECT account_id, style_id FROM garment_colors WHERE id = ?", (color_id,)
            ).fetchone()
            if color is None or color["account_id"] != account_id:
                raise HTTPException(status_code=409, detail="color_account_mismatch")
            if style_id is not None and int(color["style_id"]) != int(style_id):
                raise HTTPException(status_code=409, detail="color_style_mismatch")

    def ingest_part(self, account: sqlite3.Row, payload: dict[str, Any]) -> dict[str, Any]:
        if "account_id" in payload or any(
            isinstance(record, dict) and "account_id" in record
            for record in payload.get("records", [])
        ):
            raise HTTPException(status_code=400, detail="client_account_id_forbidden")
        required = {
            "client_batch_id", "part_number", "part_count", "schema_version",
            "observed_creator_id", "records",
        }
        if not required.issubset(payload) or payload["schema_version"] != "v3.1-task0-contract":
            raise HTTPException(status_code=400, detail="invalid_v31_part")
        if payload["observed_creator_id"] != account["expected_creator_id"]:
            raise HTTPException(status_code=403, detail="observed_creator_mismatch")
        part_number = int(payload["part_number"])
        part_count = int(payload["part_count"])
        if not 1 <= part_number <= part_count:
            raise HTTPException(status_code=400, detail="invalid_part_number")
        part_hash = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
        account_id = str(account["id"])
        client_batch_id = str(payload["client_batch_id"])

        with self._lock, self.connection:
            batch = self.connection.execute(
                "SELECT * FROM collection_batches WHERE account_id = ? AND client_batch_id = ?",
                (account_id, client_batch_id),
            ).fetchone()
            if batch is None:
                cursor = self.connection.execute(
                    """
                    INSERT INTO collection_batches(
                        account_id, client_batch_id, schema_version, observed_creator_id,
                        part_count, status
                    ) VALUES (?, ?, ?, ?, ?, 'receiving')
                    """,
                    (account_id, client_batch_id, payload["schema_version"], payload["observed_creator_id"], part_count),
                )
                batch_id = int(cursor.lastrowid)
            else:
                batch_id = int(batch["id"])
                if int(batch["part_count"]) != part_count:
                    raise HTTPException(status_code=409, detail="part_count_conflict")
                existing_part = self.connection.execute(
                    "SELECT part_hash FROM collection_batch_parts WHERE batch_id = ? AND part_number = ?",
                    (batch_id, part_number),
                ).fetchone()
                if existing_part is not None:
                    if existing_part["part_hash"] == part_hash:
                        return {"account_id": account_id, "idempotent": True}
                    raise HTTPException(status_code=409, detail="part_content_conflict")

            try:
                part_cursor = self.connection.execute(
                    """
                    INSERT INTO collection_batch_parts(batch_id, part_number, part_hash, record_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (batch_id, part_number, part_hash, len(payload["records"])),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="duplicate_part_content") from exc
            part_id = int(part_cursor.lastrowid)

            for record in payload["records"]:
                status = str(record.get("item_status", "success"))
                self._assert_owned_references(account_id, record)
                if status == "success":
                    required_record = {"video_id", "analysis_type", "source_snapshot_hash"}
                    if not required_record.issubset(record):
                        raise HTTPException(status_code=400, detail="invalid_success_item")
                    raw_response = record.get("raw_response_json")
                    raw_response_json = (
                        _canonical_json(raw_response) if isinstance(raw_response, dict) else None
                    )
                    normalized_curve_json = (
                        _canonical_json(_normalize_curve(raw_response))
                        if isinstance(raw_response, dict)
                        else None
                    )
                    snapshot = self.connection.execute(
                        """
                        SELECT id FROM video_analysis_snapshots
                        WHERE account_id = ? AND video_id = ? AND analysis_type = ?
                          AND source_snapshot_hash = ?
                        """,
                        (account_id, str(record["video_id"]), int(record["analysis_type"]), str(record["source_snapshot_hash"])),
                    ).fetchone()
                    if snapshot is None:
                        snapshot_cursor = self.connection.execute(
                            """
                            INSERT INTO video_analysis_snapshots(
                                account_id, video_id, analysis_type, source_snapshot_hash,
                                raw_response_json, normalized_curve_json
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                account_id,
                                str(record["video_id"]),
                                int(record["analysis_type"]),
                                str(record["source_snapshot_hash"]),
                                raw_response_json,
                                normalized_curve_json,
                            ),
                        )
                        snapshot_id = int(snapshot_cursor.lastrowid)
                    else:
                        snapshot_id = int(snapshot["id"])
                    raw_record_hash: str | None = hashlib.sha256(
                        _canonical_json(record).encode()
                    ).hexdigest()
                else:
                    snapshot_id = None
                    raw_record_hash = None
                self.connection.execute(
                    """
                    INSERT INTO collection_items(
                        account_id, batch_id, part_id, snapshot_id, raw_record_hash, item_status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (account_id, batch_id, part_id, snapshot_id, raw_record_hash, status),
                )
        return {"account_id": account_id, "idempotent": False}

    def missing_parts(self, account_id: str, client_batch_id: str) -> list[int]:
        batch = self._batch(account_id, client_batch_id)
        received = {
            int(row["part_number"])
            for row in self.connection.execute(
                "SELECT part_number FROM collection_batch_parts WHERE batch_id = ?", (batch["id"],)
            )
        }
        return [number for number in range(1, int(batch["part_count"]) + 1) if number not in received]

    def finalize(self, account_id: str, client_batch_id: str) -> dict[str, str]:
        with self._lock, self.connection:
            batch = self._batch(account_id, client_batch_id)
            missing = self.missing_parts(account_id, client_batch_id)
            if missing:
                raise HTTPException(status_code=409, detail="missing_parts")
            hashes = [
                row["part_hash"]
                for row in self.connection.execute(
                    """
                    SELECT part_hash FROM collection_batch_parts
                    WHERE batch_id = ? ORDER BY part_number
                    """,
                    (batch["id"],),
                )
            ]
            batch_hash = hashlib.sha256("|".join(hashes).encode()).hexdigest()
            self.connection.execute(
                "UPDATE collection_batches SET status = 'completed', batch_hash = ? WHERE id = ?",
                (batch_hash, batch["id"]),
            )
        return {"status": "completed", "batch_hash": batch_hash, "account_id": account_id}

    def _batch(self, account_id: str, client_batch_id: str) -> sqlite3.Row:
        batch = self.connection.execute(
            "SELECT * FROM collection_batches WHERE account_id = ? AND client_batch_id = ?",
            (account_id, client_batch_id),
        ).fetchone()
        if batch is None:
            raise HTTPException(status_code=404, detail="batch_not_found")
        return batch

    def contract_state(self, account_id: str) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM video_analysis_snapshots WHERE account_id = ?) AS snapshot_count,
                (SELECT COUNT(*) FROM collection_items WHERE account_id = ? AND snapshot_id IS NOT NULL) AS snapshot_reference_count,
                (SELECT COUNT(*) FROM collection_items WHERE account_id = ? AND raw_record_hash IS NULL) AS null_raw_record_hash_item_count
            """,
            (account_id, account_id, account_id),
        ).fetchone()
        return {key: int(row[key]) for key in row.keys()}


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="upload_token_required")
    return authorization.removeprefix("Bearer ")


def create_v31_contract_app() -> FastAPI:
    """Build the unregistered, v3.1-only Task 0 contract application."""

    store = V31ContractStore()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.close()

    app = FastAPI(title="Douyin color-analysis v3.1 Task 0 contract proof", lifespan=lifespan)
    app.state.task0_v31_contract_store = store

    def account(authorization: str | None) -> sqlite3.Row:
        return store.account_for_token(_token_from_header(authorization))

    @app.post("/task0/douyin-color-v31/styles")
    def create_style(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        actor = account(authorization)
        return {"data": store.create_style(str(actor["id"]), str(payload["style_code"]))}

    @app.post("/task0/douyin-color-v31/colors")
    def create_color(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        actor = account(authorization)
        return {"data": store.create_color(str(actor["id"]), int(payload["style_id"]), str(payload["color_code"]))}

    @app.post("/task0/douyin-color-v31/parts")
    async def receive_part(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        if request.headers.get("content-encoding", "").lower() != "gzip":
            raise HTTPException(status_code=415, detail="gzip_required")
        try:
            payload = json.loads(gzip.decompress(await request.body()))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="invalid_gzip_json") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="invalid_v31_part")
        return {"data": store.ingest_part(account(authorization), payload)}

    @app.get("/task0/douyin-color-v31/collection-batches/{client_batch_id}/missing-parts")
    def missing_parts(client_batch_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        actor = account(authorization)
        return {"data": {"missing_part_numbers": store.missing_parts(str(actor["id"]), client_batch_id)}}

    @app.post("/task0/douyin-color-v31/collection-batches/{client_batch_id}/finalize")
    def finalize(client_batch_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        actor = account(authorization)
        return {"data": store.finalize(str(actor["id"]), client_batch_id)}

    @app.get("/task0/douyin-color-v31/contract-state")
    def contract_state(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        actor = account(authorization)
        return {"data": store.contract_state(str(actor["id"]))}

    @app.get("/task0/douyin-color-v31/videos/{video_id}/trace", response_class=HTMLResponse)
    def trace(video_id: str, authorization: str | None = Header(default=None)) -> HTMLResponse:
        actor = account(authorization)
        snapshot = store.connection.execute(
            """
            SELECT normalized_curve_json FROM video_analysis_snapshots
            WHERE account_id = ? AND video_id = ? AND raw_response_json IS NOT NULL
            ORDER BY id DESC LIMIT 1
            """,
            (str(actor["id"]), video_id),
        ).fetchone()
        if snapshot is None:
            raise HTTPException(status_code=404, detail="trace_not_found")
        safe_video_id = html.escape(video_id)
        safe_curve = html.escape(snapshot["normalized_curve_json"])
        return HTMLResponse(
            f"<main><h1>{safe_video_id}</h1><p>raw snapshot recorded</p>"
            f"<p>normalized curve</p><pre>{safe_curve}</pre></main>"
        )

    return app
