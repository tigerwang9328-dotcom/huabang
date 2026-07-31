"""v4.0 outfit combination and split-ranking primitives.

Pure functions for:
- classifying garment_position
- building deterministic outfit combination keys
- deriving qualifying participants from clips
- determining single-garment vs outfit ranking eligibility
- mapping garment_position to ranking buckets (top/bottom)
"""

from __future__ import annotations

from typing import Iterable

_VALID_GARMENT_POSITIONS = {"outer", "top", "bottom", "none"}
_RANKING_POSITIONS = {"outer", "top", "bottom"}
# Business order for combination key: outer -> top -> bottom
_POSITION_SORT_ORDER = {"outer": 0, "top": 1, "bottom": 2}


class OutfitCompositionError(ValueError):
    """A request violates the v4.0 outfit composition contract."""


def classify_garment_position_for_ranking(value: str) -> str:
    """Validate and normalise a garment_position value."""

    if value not in _VALID_GARMENT_POSITIONS:
        raise OutfitCompositionError("invalid_garment_position")
    return value


def split_ranking_bucket(garment_position: str) -> str | None:
    """Map garment_position to a ranking bucket: top (includes outer) / bottom / None."""

    if garment_position in ("outer", "top"):
        return "top"
    if garment_position == "bottom":
        return "bottom"
    return None


def is_eligible_for_single_ranking(
    *, focus_status: str, annotation_status: str, overlap_status: str
) -> bool:
    """Single-garment ranking eligibility reuses v3.1 clear_primary semantics."""

    return (
        focus_status == "clear_primary"
        and annotation_status == "approved"
        and overlap_status in {"not_required", "approved"}
    )


def _is_qualifying_clip(clip: dict) -> bool:
    """A clip qualifies for outfit participation if clear_primary+approved+overlap approved."""

    return (
        clip.get("focus_status") == "clear_primary"
        and clip.get("annotation_status") == "approved"
        and clip.get("overlap_status") in {"not_required", "approved"}
        and clip.get("garment_position") in _RANKING_POSITIONS
    )


def derive_outfit_participants(clips: Iterable[dict]) -> list[dict]:
    """Collect qualifying clips (clear_primary+approved+overlap ok) with valid garment_position."""

    return [
        {
            "garment_position": clip["garment_position"],
            "style_id": clip["style_id"],
            "color_id": clip["color_id"],
        }
        for clip in clips
        if _is_qualifying_clip(clip)
    ]


def is_eligible_for_outfit_ranking(clips: Iterable[dict]) -> bool:
    """Outfit ranking requires at least 2 qualifying garments in the same video."""

    participants = derive_outfit_participants(clips)
    return len(participants) >= 2


def build_combination_key(participants: list[dict]) -> str:
    """Build a deterministic combination key sorted by business position order.

    Business order: outer -> top -> bottom.
    Key format: "position:style_id:color_id|position:style_id:color_id|..."
    """

    if len(participants) < 2:
        raise OutfitCompositionError("insufficient_participants")

    for p in participants:
        pos = p.get("garment_position")
        if pos not in _RANKING_POSITIONS:
            raise OutfitCompositionError("invalid_garment_position")
        if p.get("style_id") is None or p.get("color_id") is None:
            raise OutfitCompositionError("missing_style_or_color")

    sorted_participants = sorted(
        participants,
        key=lambda p: _POSITION_SORT_ORDER.get(p["garment_position"], 99),
    )
    parts = [
        f"{p['garment_position']}:{p['style_id']}:{p['color_id']}"
        for p in sorted_participants
    ]
    return "|".join(parts)
