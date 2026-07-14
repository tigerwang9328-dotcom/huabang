from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_inventory_daily_sync_writes_beijing_business_date() -> None:
    script = (REPO / "scripts" / "sync_baison_inventory_daily.sh").read_text(encoding="utf-8")

    assert "STAT_DATE=$(TZ='Asia/Shanghai' date '+%Y-%m-%d')" in script
    assert 'HUABANG_INVENTORY_STAT_DATE="$STAT_DATE"' in script
    assert "from datetime import date" in script
    assert 'STAT_DATE = date.fromisoformat(os.environ["HUABANG_INVENTORY_STAT_DATE"])' in script
    assert "SELECT CAST(:stat_date AS date)," in script
    assert '"stat_date": STAT_DATE' in script
    assert "SELECT CURRENT_DATE," not in script
