"""
财务中心 - 导出/导入服务
========================================
Excel 导出：overview / details / store-ranking → .xlsx
Excel 导入：费用批量导入
"""
import io
from datetime import date
from typing import Optional
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import finance_service
from app.models.finance import FinanceFee


# ── 样式常量 ──
_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
_THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


def _style_header(ws, col_count: int):
    """给第一行加表头样式"""
    for col in range(1, col_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER


# ══════════════════════════════════════════════════════════════
# 1. 导出财务明细
# ══════════════════════════════════════════════════════════════

async def export_details(db: AsyncSession, month: str, store_id: Optional[int] = None) -> bytes:
    """导出按日+店铺的财务明细为 Excel"""
    # 拿全量（不分页）
    data = await finance_service.get_details(db, month, store_id, page=1, page_size=9999)
    rows = data["rows"]

    wb = Workbook()
    ws = wb.active
    ws.title = f"财务明细_{month}"

    headers = ["日期", "店铺", "销售额", "退款额", "成本", "广告费", "经营利润", "订单数", "发货件数"]
    ws.append(headers)
    _style_header(ws, len(headers))

    for r in rows:
        ws.append([
            r["biz_date"], r["store_name"], r["sales"], r["refund"],
            r["cogs"], r["ad_cost"], r["profit"], r["orders"], r["qty"],
        ])

    # 列宽
    for col_letter, width in [("A", 12), ("B", 30), ("C", 14), ("D", 14), ("E", 14), ("F", 14), ("G", 14), ("H", 10), ("I", 10)]:
        ws.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
# 2. 导出店铺排行
# ══════════════════════════════════════════════════════════════

async def export_store_ranking(db: AsyncSession, month: str) -> bytes:
    """导出店铺利润排行为 Excel"""
    rows = await finance_service.get_store_ranking(db, month, limit=200)

    wb = Workbook()
    ws = wb.active
    ws.title = f"店铺排行_{month}"

    headers = ["排名", "店铺", "平台", "销售额", "退款额", "成本", "广告费", "毛利", "利润率%"]
    ws.append(headers)
    _style_header(ws, len(headers))

    for i, r in enumerate(rows, 1):
        ws.append([
            i, r["store_name"], r["platform"], r["sales"], r["refund"],
            r["cogs"], r["ad_cost"], r["gross_profit"], r["profit_rate"],
        ])

    for col_letter, width in [("A", 6), ("B", 35), ("C", 12), ("D", 14), ("E", 14), ("F", 14), ("G", 14), ("H", 14), ("I", 10)]:
        ws.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
# 3. 费用导入模板
# ══════════════════════════════════════════════════════════════

def generate_fee_import_template() -> bytes:
    """生成费用导入 Excel 模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "费用导入"

    headers = ["日期(YYYY-MM-DD)", "费用类型", "说明", "关联店铺(可选)", "金额", "备注(可选)"]
    ws.append(headers)
    _style_header(ws, len(headers))

    # 示例行
    ws.append(["2026-04-01", "ad", "抖音千川投放", "49.Jarek Wolflike官方旗舰店", 5000.00, ""])
    ws.append(["2026-04-01", "logistics", "4月第1批快递", "", 3200.50, "中通"])
    ws.append(["2026-04-01", "packing", "包装袋采购", "", 800.00, ""])

    # 说明Sheet
    ws2 = wb.create_sheet("说明")
    ws2.append(["费用类型代码", "含义"])
    for code, label in [("ad", "广告投放"), ("logistics", "快递物流"), ("commission", "平台佣金"),
                         ("labor", "人工成本"), ("packing", "包材费用"), ("other", "其他")]:
        ws2.append([code, label])

    for col_letter, width in [("A", 18), ("B", 14), ("C", 25), ("D", 30), ("E", 12), ("F", 20)]:
        ws.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
# 4. 费用批量导入
# ══════════════════════════════════════════════════════════════

async def import_fees(db: AsyncSession, file_bytes: bytes, user_id: int) -> dict:
    """
    从 Excel 批量导入费用记录。
    返回: {"imported": N, "errors": [...]}
    """
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active

    valid_types = {"ad", "logistics", "commission", "labor", "packing", "other"}
    imported = 0
    errors = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not row[0]:
            continue
        try:
            fee_date = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]).strip()[:10])
            fee_type = str(row[1]).strip().lower() if row[1] else "other"
            if fee_type not in valid_types:
                errors.append(f"第{row_idx}行: 无效费用类型 '{fee_type}'")
                continue
            description = str(row[2]).strip() if row[2] else None
            store_name = str(row[3]).strip() if row[3] else None
            amount = float(row[4]) if row[4] else 0
            remark = str(row[5]).strip() if row[5] and len(row) > 5 else None

            fee = FinanceFee(
                fee_date=fee_date, fee_type=fee_type, description=description,
                store_name=store_name, amount=amount, remark=remark,
                created_by=user_id,
            )
            db.add(fee)
            imported += 1
        except Exception as e:
            errors.append(f"第{row_idx}行: {str(e)}")

    if imported > 0:
        await db.flush()

    return {"imported": imported, "errors": errors[:20]}  # 最多返回20条错误
