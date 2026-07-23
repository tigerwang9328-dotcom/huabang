"""
销售月报 - Excel 导出（v3：完整月报字段）
==========================================
三种导出：
  export_report_excel    销售月报店铺级（33字段，对齐月报.xlsx模板）
  export_pending_excel   待结算订单明细
  export_abnormal_excel  异常订单明细

均返回 bytes，由 API 层包装为 Response 下载。
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=10)
_HEADER_FILL  = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
_TITLE_FONT   = Font(bold=True, size=12)
_CENTER       = Alignment(horizontal="center", vertical="center", wrap_text=False)
_RIGHT        = Alignment(horizontal="right",  vertical="center")
_LEFT         = Alignment(horizontal="left",   vertical="center")
_THIN         = Side(style="thin", color="BBBBBB")
_BORDER       = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _to_xlsx_value(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


def _save(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _set_col_widths(ws, col_widths: list[int]):
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ─── 完整月报字段定义 ─────────────────────────────────────
# (列头, DB字段名, 对齐, 列宽)
_FULL_REPORT_COLS: list[tuple[str, str, str, int]] = [
    # 基本信息
    ("序号",           "__seq__",              "center", 6),
    ("店铺编号",        "store_code",           "left",   12),
    ("店铺",           "store_name",           "left",   18),
    # 发货 / 退款
    ("发货订单数",      "shipped_order_count",  "right",  10),
    ("发货金额",        "shipped_amount",       "right",  12),
    ("退款订单数",      "refund_order_count",   "right",  10),
    ("发货后退款金额",   "after_ship_refund_amount", "right", 14),
    ("发货前退款金额",   "before_ship_refund_amount", "right", 14),
    ("结算后退款金额",   "after_settlement_refund_amount", "right", 14),
    # 销售
    ("实际销售额",      "actual_sales_amount",       "right", 12),
    ("实销单量",        "actual_sales_order_count",  "right", 10),
    ("实际销售订单",    "actual_sales_order_completed", "right", 11),
    ("已付款销售额",    "paid_sales_amount",         "right", 12),
    ("客单价",          "avg_order_amount",          "right", 10),
    # 成本费用（全部按顺序）
    ("实际销售成本",    "actual_product_cost",       "right", 12),
    ("平台服务费",      "platform_service_fee",      "right", 11),
    ("达人佣金",        "talent_commission",         "right", 10),
    ("退货损耗",        "return_loss",               "right", 10),
    ("运费",            "freight_amount",            "right", 10),
    ("包装费",          "package_fee",               "right", 10),
    ("运费险",          "freight_insurance",         "right", 10),
    ("消费者赔付",      "compensation_amount",       "right", 10),
    ("小额打款",        "small_payment_amount",      "right", 10),
    ("平台其他费用",    "platform_other_fee",        "right", 12),
    ("外包客服费用",    "customer_service_fee",      "right", 12),
    ("推广消耗",        "ad_cost",                   "right", 10),
    ("人员工资",        "salary_fee",                "right", 10),
    ("房租水电",        "rent_utility_fee",          "right", 10),
    ("本月其他支出",    "other_monthly_expense",     "right", 12),
    ("税费",            "tax_fee",                   "right", 10),
    ("费用合计",        "total_fee",                 "right", 11),
    # 利润
    ("订单理赔",        "order_claim",               "right", 10),
    ("货值损耗",        "goods_loss",                "right", 10),
    ("毛利",            "gross_profit",              "right", 10),
    ("保证金充值",      "deposit_recharge",          "right", 11),
    ("返佣返点",        "rebate_amount",             "right", 10),
    ("净利润",          "net_profit",                "right", 10),
    ("净利润率",        "net_profit_rate",           "right", 10),
    ("总退款率",        "total_refund_rate",         "right", 10),
    ("发货前退款率",    "before_ship_refund_rate",   "right", 11),
    ("发货后退款率",    "after_ship_refund_rate",    "right", 11),
    ("结算后退款率",    "after_settlement_refund_rate", "right", 12),
]


def export_report_excel(
    month: str,
    shop_rows: Iterable[dict],
    batch_name: str = "",
) -> bytes:
    """生成完整月报 Excel（33列，带标题行）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = f"销售月报-{month}"

    headers = [col[0] for col in _FULL_REPORT_COLS]
    col_widths = [col[3] for col in _FULL_REPORT_COLS]

    # ── 第1行：报表标题 ───────────────────────────────────
    title = batch_name or f"{month}-销售月报"
    ws.merge_cells(start_row=1, start_column=1,
                   end_row=1,   end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font      = _TITLE_FONT
    title_cell.alignment = _CENTER
    ws.row_dimensions[1].height = 22

    # ── 第2行：表头 ───────────────────────────────────────
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER
        cell.border    = _BORDER
    ws.row_dimensions[2].height = 18

    # ── 数据行（从第3行开始）────────────────────────────────
    rows = list(shop_rows)
    for i, row in enumerate(rows, start=1):
        excel_row = i + 2
        for col_idx, (_, field, align, _w) in enumerate(_FULL_REPORT_COLS, start=1):
            if field == "__seq__":
                val = i
            else:
                raw = row.get(field)
                if raw is None:
                    # 整数字段
                    if field in ("shipped_order_count", "refund_order_count",
                                 "actual_sales_order_count", "actual_sales_order_completed"):
                        val = 0
                    elif field.endswith("_rate"):
                        val = 0.0
                    else:
                        val = None   # 店铺编号等字符串字段
                elif field.endswith("_rate"):
                    val = round(float(_to_xlsx_value(raw)) * 100, 2)
                else:
                    val = _to_xlsx_value(raw)
            cell = ws.cell(row=excel_row, column=col_idx, value=val)
            cell.border = _BORDER
            if align == "right":
                cell.alignment = _RIGHT
                # 百分比字段加 %
                if field.endswith("_rate") and val is not None:
                    cell.number_format = '0.00"%"'
                elif field not in ("shipped_order_count", "refund_order_count",
                                   "actual_sales_order_count", "actual_sales_order_completed", "__seq__"):
                    cell.number_format = '#,##0.00'
            elif align == "center":
                cell.alignment = _CENTER
            else:
                cell.alignment = _LEFT

    # ── 合计行 ─────────────────────────────────────────────
    if rows:
        sum_row = len(rows) + 3
        sum_fields = {col[1] for col in _FULL_REPORT_COLS
                      if col[2] == "right" and col[1] != "__seq__"}
        int_fields = {"shipped_order_count", "refund_order_count", "actual_sales_order_count",
                      "actual_sales_order_completed"}
        for col_idx, (_, field, align, _w) in enumerate(_FULL_REPORT_COLS, start=1):
            cell = ws.cell(row=sum_row, column=col_idx)
            cell.border = _BORDER
            cell.font   = Font(bold=True)
            if col_idx == 1:
                cell.value     = "合计"
                cell.alignment = _CENTER
            elif field in sum_fields and not field.endswith("_rate"):
                total = sum(
                    float(_to_xlsx_value(r.get(field) or 0))
                    for r in rows
                )
                cell.value = round(total, 2)
                cell.alignment = _RIGHT
                if field not in int_fields:
                    cell.number_format = '#,##0.00'

    _set_col_widths(ws, col_widths)

    # 冻结前3列（序号+店铺编号+店铺）
    ws.freeze_panes = "D3"

    return _save(wb)


# ─── 待结算订单明细 ───────────────────────────────────────
_PENDING_HEADERS = [
    "店铺", "主订单号", "子订单号", "商品编码", "商品名称", "SKU",
    "数量", "发货时间", "订单状态", "售后状态",
    "应付金额", "应收金额", "收款金额", "退款金额", "判定原因",
]

_PENDING_FIELDS = [
    "store_name", "main_order_no", "sub_order_no", "product_code", "product_name", "sku_name",
    "quantity", "ship_time", "order_status", "after_sale_status",
    "order_pay_amount", "receivable_amount", "settlement_income", "refund_goods_amount",
    "final_status_reason",
]


def _write_simple_header(ws, headers: list[str]):
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER


def export_pending_excel(month: str, order_rows: Iterable[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"待结算-{month}"
    _write_simple_header(ws, _PENDING_HEADERS)
    for i, row in enumerate(order_rows, start=2):
        for j, field in enumerate(_PENDING_FIELDS, start=1):
            ws.cell(row=i, column=j, value=_to_xlsx_value(row.get(field)))
    for col_idx in range(1, len(_PENDING_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16
    return _save(wb)


# ─── 异常订单明细 ─────────────────────────────────────────
_ABNORMAL_HEADERS = [
    "店铺", "主订单号", "子订单号", "商品编码", "商品名称",
    "数量", "订单状态", "售后状态",
    "应付金额", "应收金额", "收款金额", "退款金额", "资金退款",
    "异常原因",
]

_ABNORMAL_FIELDS = [
    "store_name", "main_order_no", "sub_order_no", "product_code", "product_name",
    "quantity", "order_status", "after_sale_status",
    "order_pay_amount", "receivable_amount", "settlement_income",
    "refund_goods_amount", "fund_refund_amount",
    "abnormal_reason",
]


def export_abnormal_excel(month: str, order_rows: Iterable[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"异常订单-{month}"
    _write_simple_header(ws, _ABNORMAL_HEADERS)
    for i, row in enumerate(order_rows, start=2):
        for j, field in enumerate(_ABNORMAL_FIELDS, start=1):
            ws.cell(row=i, column=j, value=_to_xlsx_value(row.get(field)))
    for col_idx in range(1, len(_ABNORMAL_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16
    return _save(wb)


# ─── 正常订单明细（用于核对计算逻辑）─────────────────────────
_NORMAL_HEADERS = [
    "店铺", "主订单编号", "子订单编号", "商品编码", "商品名称", "商品数量", "发货时间",
    "订单状态", "售后状态", "最终状态", "命中规则", "规则说明",
    "订单应付金额", "商品金额", "应收金额", "订单运费",
    "平台费用", "达人佣金", "结算金额", "收款金额", "结算差异", "退款金额", "资金退款",
    "商品成本价", "商品成本金额", "快递公司", "快递单号", "快递费", "订单分类标签",
    "是否计入实际销售额", "是否计入发货后退款金额", "是否计入实销单量", "是否计入实际销售成本",
    "计算备注",
]

_STATUS_CN = {
    "pre_settlement_refund": "结算前退款", "paid": "已收款",
    "refunded": "已退款", "pending_settlement": "待结算",
}

# Excel 单表最大 1,048,576 行（含表头），数据行上限取 1,048,575
_MAX_DATA_ROWS_PER_SHEET = 1_048_575


def _q(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _normal_row(row: dict) -> list:
    fs = row.get("final_status")
    inc = _q(row.get("settlement_income"))
    refund = _q(row.get("refund_goods_amount"))
    cost_price = _q(row.get("product_cost_price"))
    in_sales        = "是" if (fs == "paid" and inc != 0) else "否"
    in_refund       = "是" if fs in ("refunded", "pre_settlement_refund") else "否"
    in_order_count  = "是" if fs == "paid" else "否"
    in_goods_value  = "是" if (row.get("ship_time") and cost_price != 0) else "否"
    reason = row.get("final_status_reason") or ""
    note = row.get("final_status_reason") or row.get("abnormal_reason") or ""
    return [
        row.get("store_name"), row.get("main_order_no"), row.get("sub_order_no"),
        row.get("product_code"), row.get("product_name"),
        int(row.get("quantity") or 0),
        _to_xlsx_value(row.get("ship_time")),
        row.get("order_status"), row.get("after_sale_status"),
        _STATUS_CN.get(fs, fs), reason, reason,
        _to_xlsx_value(row.get("order_pay_amount")),
        _to_xlsx_value(row.get("product_amount")),
        _to_xlsx_value(row.get("receivable_amount")),
        _to_xlsx_value(row.get("order_freight")),
        _to_xlsx_value(row.get("platform_service_fee")),
        _to_xlsx_value(row.get("talent_commission")),
        _to_xlsx_value(row.get("settlement_amount_total")),
        _to_xlsx_value(row.get("settlement_income")),
        _to_xlsx_value(row.get("settlement_difference")),
        _to_xlsx_value(row.get("refund_goods_amount")),
        _to_xlsx_value(row.get("fund_refund_amount")),
        _to_xlsx_value(row.get("product_cost_price")),
        _to_xlsx_value(row.get("product_cost_amount")),
        row.get("express_company"), row.get("express_no"), _to_xlsx_value(row.get("matched_freight")),
        _STATUS_CN.get(fs, ""),
        in_sales, in_refund, in_order_count, in_goods_value, note,
    ]


def export_normal_excel(month: str, order_rows: Iterable[dict]) -> bytes:
    """
    正常订单明细导出（paid/refunded/pending_settlement，排除 abnormal）。
    write_only 流式写入，超过单表上限自动分 Sheet；无数据时导出仅含表头的空模板。
    """
    from openpyxl.cell import WriteOnlyCell
    wb = Workbook(write_only=True)

    def _new_sheet(idx: int):
        title = f"正常订单-{month}" if idx == 1 else f"正常订单{idx}"
        ws = wb.create_sheet(title=title[:31])
        hdr = []
        for h in _NORMAL_HEADERS:
            c = WriteOnlyCell(ws, value=h)
            c.font = _HEADER_FONT
            c.fill = _HEADER_FILL
            c.alignment = _CENTER
            hdr.append(c)
        ws.append(hdr)
        return ws

    sheet_idx = 1
    ws = _new_sheet(sheet_idx)
    rows_in_sheet = 0
    for row in order_rows:
        if rows_in_sheet >= _MAX_DATA_ROWS_PER_SHEET:
            sheet_idx += 1
            ws = _new_sheet(sheet_idx)
            rows_in_sheet = 0
        ws.append(_normal_row(row))
        rows_in_sheet += 1
    return _save(wb)
