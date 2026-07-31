"""v4.0 outfit combination and split-ranking primitives.

Pure functions for:
- classifying garment_position
- building deterministic outfit combination keys
- deriving qualifying participants from clips
- determining single-garment vs outfit ranking eligibility
- mapping garment_position to ranking buckets (top/bottom)

v4.0 revised semantics: one curve (clip) maps to one whole outfit (>=2 garments).
Color is excluded from combination identity; garments are distinguished by SKU.
combination_key format: "position:style_id|position:style_id|..." (no color_id).
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
    """Single-garment ranking eligibility reuses v3.1 clear_primary semantics.

    clear_primary here means a whole outfit is clearly visible (>=2 garments).
    """

    return (
        focus_status == "clear_primary"
        and annotation_status == "approved"
        and overlap_status in {"not_required", "approved"}
    )


def _is_qualifying_clip(clip: dict) -> bool:
    """A clip qualifies for outfit participation if clear_primary+approved+overlap approved.

    v4.0: clear_primary means a whole outfit is clearly visible; the clip carries
    its garment breakdown in outfit_parts_json.
    """

    return (
        clip.get("focus_status") == "clear_primary"
        and clip.get("annotation_status") == "approved"
        and clip.get("overlap_status") in {"not_required", "approved"}
    )


def derive_outfit_participants(clips: Iterable[dict]) -> list[dict]:
    """Collect outfit parts from qualifying clips (clear_primary+approved+overlap ok).

    Each qualifying clip carries an ``outfit_parts_json`` list describing the
    garments of the whole outfit visible in that clip. Participants are
    deduplicated by (garment_position, style_id, sku_code) so multiple clips
    showing the same outfit do not double-count garments.

    Returns a list of dicts with keys: garment_position, style_id, sku_code.
    sku_code may be None when the SKU is not yet resolved.
    """

    participants: list[dict] = []
    seen: set[tuple] = set()
    for clip in clips:
        if not _is_qualifying_clip(clip):
            continue
        for part in clip.get("outfit_parts_json") or []:
            pos = part.get("position") or part.get("garment_position")
            if pos not in _RANKING_POSITIONS:
                # none/other garments never enter an outfit combination
                continue
            style_id = part.get("style_id")
            sku_code = part.get("sku_code")
            key = (pos, style_id, sku_code)
            if key in seen:
                continue
            seen.add(key)
            participants.append({
                "garment_position": pos,
                "style_id": style_id,
                "sku_code": sku_code,
            })
    return participants


def is_eligible_for_outfit_ranking(clips: Iterable[dict]) -> bool:
    """Outfit ranking requires at least 2 qualifying garments in the same video."""

    participants = derive_outfit_participants(clips)
    return len(participants) >= 2


def build_combination_key(participants: list[dict]) -> str:
    """Build a deterministic combination key sorted by business position order.

    Business order: outer -> top -> bottom.
    Key format: "position:style_id|position:style_id|..."

    Color is intentionally excluded: v4.0 distinguishes garments by SKU, not
    color, and one curve maps to one whole outfit.
    """

    if len(participants) < 2:
        raise OutfitCompositionError("insufficient_participants")

    for p in participants:
        pos = p.get("garment_position")
        if pos not in _RANKING_POSITIONS:
            raise OutfitCompositionError("invalid_garment_position")
        if p.get("style_id") is None:
            raise OutfitCompositionError("missing_style")

    sorted_participants = sorted(
        participants,
        key=lambda p: _POSITION_SORT_ORDER.get(p["garment_position"], 99),
    )
    parts = [
        f"{p['garment_position']}:{p['style_id']}"
        for p in sorted_participants
    ]
    return "|".join(parts)
