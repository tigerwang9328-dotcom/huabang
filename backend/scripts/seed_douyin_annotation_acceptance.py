"""Seed 10 placeholder annotation clips covering 7 acceptance scenarios for
the v4.0 Douyin color-analysis annotation closed loop.

The script writes directly to the ``douyin`` schema via a *synchronous*
SQLAlchemy session so it can run without an admin JWT.  Database credentials
are loaded from environment variables through ``app.core.config.settings``
(never hardcoded).  Placeholder styles / colors / SKUs are idempotent
(skip-if-exists by business code); clips are idempotent by
``(account_id, video_id, start_ms, end_ms, focus_status, annotation_status)``.

Run from the backend directory:

    cd /srv/huabang-ai-center/backend
    set -a && source .env && set +a
    PYTHONPATH=. .venv/bin/python scripts/seed_douyin_annotation_acceptance.py

Notes
-----
- v4.0 stores garment composition in ``VideoClip.outfit_parts_json``; the
  clip-level ``style_id`` / ``color_id`` are kept NULL on purpose.
- ``GarmentSku`` has no ``style_id`` column, so a SKU is associated with a
  style only through its color.  To make ``ACCEPTANCE_SKU_002`` genuinely
  belong to ``ACCEPTANCE_BOTTOM_001``, ``ACCEPTANCE_COLOR_002`` is attached
  to the bottom style (``ACCEPTANCE_COLOR_001`` stays on the top style).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.douyin_color_analytics import (
    DouyinCreatorAccount,
    GarmentColor,
    GarmentSku,
    GarmentStyle,
    Video,
    VideoClip,
)


ACCOUNT_ID = 2
ADMIN_USER_ID = 1

# Placeholder business codes for the acceptance dataset.
TOP_STYLE_CODE = "ACCEPTANCE_TOP_001"
BOTTOM_STYLE_CODE = "ACCEPTANCE_BOTTOM_001"
OUTER_STYLE_CODE = "ACCEPTANCE_OUTER_001"
COLOR_001_CODE = "ACCEPTANCE_COLOR_001"
COLOR_002_CODE = "ACCEPTANCE_COLOR_002"
SKU_001_CODE = "ACCEPTANCE_SKU_001"
SKU_002_CODE = "ACCEPTANCE_SKU_002"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_style(
    session,
    account_id: int,
    style_code: str,
    style_name: str,
    position: str,
) -> GarmentStyle:
    existing = session.execute(
        select(GarmentStyle).where(
            GarmentStyle.account_id == account_id,
            GarmentStyle.style_code == style_code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    style = GarmentStyle(
        account_id=account_id,
        style_code=style_code,
        style_name=style_name,
        garment_position=position,
        status="active",
    )
    session.add(style)
    session.flush()
    return style


def get_or_create_color(
    session,
    account_id: int,
    style_id: int,
    color_code: str,
    color_name: str,
) -> GarmentColor:
    existing = session.execute(
        select(GarmentColor).where(
            GarmentColor.account_id == account_id,
            GarmentColor.style_id == style_id,
            GarmentColor.color_code == color_code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    color = GarmentColor(
        account_id=account_id,
        style_id=style_id,
        color_code=color_code,
        color_name=color_name,
        status="active",
    )
    session.add(color)
    session.flush()
    return color


def get_or_create_sku(
    session,
    account_id: int,
    color_id: int,
    sku_code: str,
    size_name: str | None,
) -> GarmentSku:
    existing = session.execute(
        select(GarmentSku).where(
            GarmentSku.account_id == account_id,
            GarmentSku.sku_code == sku_code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    sku = GarmentSku(
        account_id=account_id,
        color_id=color_id,
        sku_code=sku_code,
        size_name=size_name,
        status="active",
    )
    session.add(sku)
    session.flush()
    return sku


def find_existing_clip(
    session,
    account_id: int,
    video_id: int,
    start_ms: int,
    end_ms: int,
    focus_status: str,
    annotation_status: str,
) -> VideoClip | None:
    return session.execute(
        select(VideoClip).where(
            VideoClip.account_id == account_id,
            VideoClip.video_id == video_id,
            VideoClip.start_ms == start_ms,
            VideoClip.end_ms == end_ms,
            VideoClip.focus_status == focus_status,
            VideoClip.annotation_status == annotation_status,
        )
    ).scalar_one_or_none()


def part(position: str, style_id: int, sku_code: str | None) -> dict[str, Any]:
    """Build one outfit_parts_json entry."""
    return {"position": position, "style_id": style_id, "sku_code": sku_code}


def main() -> None:
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as session:
        # 1. Verify the active account (id=2, reare_main_v2).
        account = session.execute(
            select(DouyinCreatorAccount).where(DouyinCreatorAccount.id == ACCOUNT_ID)
        ).scalar_one_or_none()
        if account is None:
            print(f"[ERROR] account id={ACCOUNT_ID} not found", file=sys.stderr)
            sys.exit(1)
        if account.status != "active":
            print(
                f"[ERROR] account id={ACCOUNT_ID} status={account.status!r}, expected 'active'",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"[OK] active account: id={account.id} key={account.account_key} "
            f"name={account.display_name}"
        )

        # 2. Collect videos for the account.  The 10 scenarios need 8 distinct
        #    video slots; if fewer videos exist they are reused cyclically.
        videos = (
            session.execute(
                select(Video).where(Video.account_id == ACCOUNT_ID).order_by(Video.id)
            )
            .scalars()
            .all()
        )
        if not videos:
            print("[ERROR] no videos found for account; seed cannot proceed", file=sys.stderr)
            sys.exit(1)
        video_ids = [v.id for v in videos]
        preview = video_ids[:8]
        print(
            f"[OK] videos available: {len(video_ids)} "
            f"(first ids: {preview}{'...' if len(video_ids) > 8 else ''})"
        )
        if len(video_ids) < 8:
            print(
                f"[WARN] only {len(video_ids)} videos available; "
                "scenarios will reuse videos cyclically"
            )

        def vid(idx: int) -> int:
            return video_ids[idx % len(video_ids)]

        # 3. Placeholder styles (idempotent).
        top_style = get_or_create_style(
            session, ACCOUNT_ID, TOP_STYLE_CODE, "验收占位-上装", "top"
        )
        bottom_style = get_or_create_style(
            session, ACCOUNT_ID, BOTTOM_STYLE_CODE, "验收占位-下装", "bottom"
        )
        outer_style = get_or_create_style(
            session, ACCOUNT_ID, OUTER_STYLE_CODE, "验收占位-外套", "outer"
        )
        print(
            f"[OK] styles: top={top_style.id} bottom={bottom_style.id} "
            f"outer={outer_style.id}"
        )

        # 4. Placeholder colors (idempotent).
        #    COLOR_001 -> TOP (drives SKU_001 under TOP).
        #    COLOR_002 -> BOTTOM (drives SKU_002 under BOTTOM).
        color_001 = get_or_create_color(
            session, ACCOUNT_ID, top_style.id, COLOR_001_CODE, "验收占位色-01"
        )
        color_002 = get_or_create_color(
            session, ACCOUNT_ID, bottom_style.id, COLOR_002_CODE, "验收占位色-02"
        )
        print(
            f"[OK] colors: color_001={color_001.id} (->top) "
            f"color_002={color_002.id} (->bottom)"
        )

        # 5. Placeholder SKUs (idempotent).
        sku_001 = get_or_create_sku(
            session, ACCOUNT_ID, color_001.id, SKU_001_CODE, "M"
        )
        sku_002 = get_or_create_sku(
            session, ACCOUNT_ID, color_002.id, SKU_002_CODE, "M"
        )
        print(
            f"[OK] skus: sku_001={sku_001.id} (->color_001/top) "
            f"sku_002={sku_002.id} (->color_002/bottom)"
        )

        # 6. Build the 10 acceptance scenarios.
        top_bottom_parts = [
            part("top", top_style.id, SKU_001_CODE),
            part("bottom", bottom_style.id, SKU_002_CODE),
        ]
        outer_top_bottom_parts = [
            part("outer", outer_style.id, None),
            part("top", top_style.id, SKU_001_CODE),
            part("bottom", bottom_style.id, SKU_002_CODE),
        ]

        ts = now_utc()
        # Tuple shape:
        # (label, video_idx, start_ms, end_ms, focus_status, outfit_parts,
        #  annotation_status, overlap_reason, overlap_status, deleted_at)
        scenarios: list[tuple] = [
            ("1.clear_primary(top+bottom)", 0, 0, 5000, "clear_primary",
             top_bottom_parts, "submitted", None, "not_required", None),
            ("2.clear_primary(top+bottom)", 1, 0, 5000, "clear_primary",
             top_bottom_parts, "approved", None, "not_required", None),
            ("3.clear_primary(top+bottom)", 2, 0, 5000, "clear_primary",
             top_bottom_parts, "rejected", None, "not_required", None),
            ("4.clear_primary(outer+top+bottom)", 3, 0, 5000, "clear_primary",
             outer_top_bottom_parts, "submitted", None, "not_required", None),
            ("5.multi_focus", 4, 0, 5000, "multi_focus",
             [], "draft", None, "not_required", None),
            ("6.unclear", 5, 0, 5000, "unclear",
             [], "draft", None, "not_required", None),
            # Same combination as scenario 1, different time range on the same video.
            ("7.same-combo-reappear", 0, 5000, 10000, "clear_primary",
             top_bottom_parts, "approved", None, "not_required", None),
            # Time-overlaps scenario 1 (0-5000) on the same video; cross-color overlap.
            ("8.cross-color-overlap", 0, 2000, 7000, "clear_primary",
             top_bottom_parts, "submitted", "cross_color_overlap",
             "pending_approval", None),
            # Created then soft-deleted.
            ("9.delete-and-recover", 6, 0, 5000, "clear_primary",
             top_bottom_parts, "deleted", None, "not_required", ts),
            ("10.clear_primary(top+bottom)", 7, 0, 5000, "clear_primary",
             top_bottom_parts, "draft", None, "not_required", None),
        ]

        created_clip_ids: list[int] = []
        skipped_clip_ids: list[int] = []
        for (
            label, vidx, start_ms, end_ms, focus_status, outfit_parts,
            ann_status, overlap_reason, overlap_status, deleted_at,
        ) in scenarios:
            video_id = vid(vidx)
            existing = find_existing_clip(
                session, ACCOUNT_ID, video_id, start_ms, end_ms,
                focus_status, ann_status,
            )
            if existing is not None:
                skipped_clip_ids.append(existing.id)
                print(
                    f"[SKIP] {label}: existing clip id={existing.id} "
                    f"(video_id={video_id} {start_ms}-{end_ms} status={ann_status})"
                )
                continue
            clip = VideoClip(
                account_id=ACCOUNT_ID,
                video_id=video_id,
                style_id=None,
                color_id=None,
                start_ms=start_ms,
                end_ms=end_ms,
                input_start_ms=start_ms,
                input_end_ms=end_ms,
                curve_resolution_ms=1000,
                focus_status=focus_status,
                outfit_parts_json=outfit_parts,
                focus_note=None,
                annotation_status=ann_status,
                overlap_reason=overlap_reason,
                overlap_status=overlap_status,
                overlap_approved_by=None,
                overlap_approved_at=None,
                submitted_by=None,
                submitted_at=None,
                approved_by=None,
                approved_at=None,
                created_by=ADMIN_USER_ID,
                created_at=ts,
                updated_by=ADMIN_USER_ID,
                updated_at=ts,
                version=1,
                deleted_at=deleted_at,
            )
            session.add(clip)
            session.flush()
            created_clip_ids.append(clip.id)
            print(
                f"[CREATE] {label}: clip id={clip.id} "
                f"(video_id={video_id} {start_ms}-{end_ms} status={ann_status})"
            )

        session.commit()

        # 7. Summary + scenario coverage confirmation.
        print("\n=== Acceptance seed summary ===")
        print(f"styles: top={top_style.id} bottom={bottom_style.id} outer={outer_style.id}")
        print(
            f"colors: color_001={color_001.id} (->top) "
            f"color_002={color_002.id} (->bottom)"
        )
        print(
            f"skus: sku_001={sku_001.id} (->color_001) "
            f"sku_002={sku_002.id} (->color_002)"
        )
        print(f"clips created: {created_clip_ids}")
        print(f"clips skipped (already existed): {skipped_clip_ids}")

        coverage = {
            "clear_primary 2 parts (top+bottom) - scenario 1": any(s[0].startswith("1.") for s in scenarios),
            "clear_primary 2 parts - sample threshold (2,3,10)": (
                any(s[0].startswith("2.") for s in scenarios)
                and any(s[0].startswith("3.") for s in scenarios)
                and any(s[0].startswith("10.") for s in scenarios)
            ),
            "clear_primary 3 parts (outer+top+bottom) - scenario 4": any(s[0].startswith("4.") for s in scenarios),
            "multi_focus (0 parts) - scenario 5": any(s[0].startswith("5.") for s in scenarios),
            "unclear (0 parts) - scenario 6": any(s[0].startswith("6.") for s in scenarios),
            "same combination reappear - scenario 7": any(s[0].startswith("7.") for s in scenarios),
            "cross-color overlap pending approval - scenario 8": any(s[0].startswith("8.") for s in scenarios),
            "deleted (delete & recover) - scenario 9": any(s[0].startswith("9.") for s in scenarios),
        }
        print("scenario coverage:")
        all_ok = True
        for k, v in coverage.items():
            mark = "OK" if v else "MISSING"
            if not v:
                all_ok = False
            print(f"  - [{mark}] {k}")
        print(f"\nacceptance scenarios covered: {sum(coverage.values())}/{len(coverage)}")
        if not all_ok:
            sys.exit(2)


if __name__ == "__main__":
    main()
