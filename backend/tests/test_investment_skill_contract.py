"""Repository mirror contract for the investment optimizer Skill."""

from pathlib import Path


def test_investment_skill_documents_history_and_region_semantics():
    text = Path("../docs/skills/huabang-douyin-laike-optimizer.md").read_text("utf-8")

    for required in (
        "investment-decisions/history",
        "requires_human_confirm: true",
        "region_province",
        "region_city",
        "投放触达人群居住地",
        "24/72/168",
        "DeepSeek",
        "规则兜底",
        "不直接执行投放",
    ):
        assert required in text
