"""
销售月报 - 文件解析器
=====================
各文件类型的 Excel 解析逻辑。
"""
from __future__ import annotations
import io
import os
import csv as _csv
import logging
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# ─── 文件格式 / 统一读取层 ─────────────────────────────────
# 工作簿上传只接受真正的多 Sheet Excel 工作簿
WORKBOOK_EXTS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
# 单表上传接受的扩展名（.xls 视环境是否安装 pandas+xlrd 而定）
SINGLE_TABLE_EXTS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".csv", ".xls"}
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb18030")


def get_file_ext(filename: str | None) -> str:
    """返回小写扩展名（含点），无法识别返回空串。"""
    if not filename:
        return ""
    return os.path.splitext(str(filename))[1].lower()


def _xls_supported() -> bool:
    """.xls 需要 pandas + xlrd，按需探测。"""
    try:
        import pandas  # noqa: F401
        import xlrd     # noqa: F401
        return True
    except Exception:
        return False


def check_workbook_ext(filename: str | None) -> None:
    """工作簿上传扩展名校验：只允许 .xlsx/.xlsm/.xltx/.xltm。"""
    ext = get_file_ext(filename)
    if ext == ".csv":
        raise ValueError("CSV 文件没有多个工作表，不能作为工作簿上传。请切换到“单表上传”。")
    if ext not in WORKBOOK_EXTS:
        raise ValueError("工作簿上传只支持 .xlsx/.xlsm/.xltx/.xltm，CSV 请使用单表上传。")


def check_single_table_ext(filename: str | None) -> None:
    """单表上传扩展名校验：xlsx/xlsm/xltx/xltm/csv 均可；.xls 视环境而定。"""
    ext = get_file_ext(filename)
    if ext in WORKBOOK_EXTS or ext == ".csv":
        return
    if ext == ".xls":
        if not _xls_supported():
            raise ValueError("暂不支持 .xls，请另存为 .xlsx 后上传。")
        return
    raise ValueError(f"不支持的文件格式：{ext or '未知'}，请上传 .xlsx 或 .csv 文件。")


def read_csv_rows(file_path) -> list[list]:
    """
    读取 CSV → 二维 rows（每格为 str）。
    - 依次尝试 utf-8-sig / utf-8 / gbk / gb18030 编码
    - 分隔符优先逗号，失败时自动 sniff
    - 跳过全空行
    """
    raw: str | None = None
    for enc in _CSV_ENCODINGS:
        try:
            with open(file_path, "r", encoding=enc, newline="") as fh:
                raw = fh.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if raw is None:
        raise ValueError("CSV 文件编码无法识别（已尝试 utf-8-sig/utf-8/gbk/gb18030）。")

    delimiter = ","
    try:
        dialect = _csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    rows: list[list] = []
    for r in _csv.reader(io.StringIO(raw), delimiter=delimiter):
        if not any((str(c).strip() if c is not None else "") for c in r):
            continue  # 跳过空行
        rows.append([c.strip() if isinstance(c, str) else c for c in r])

    if not rows:
        raise ValueError("CSV 文件为空或未读取到有效数据。")
    return rows


def _read_xls_rows(file_path) -> list[list]:
    """.xls → rows（需 pandas+xlrd）。"""
    import pandas as pd
    df = pd.read_excel(file_path, header=None, dtype=object, engine="xlrd")
    rows: list[list] = []
    for _, row in df.iterrows():
        vals = [None if pd.isna(v) else v for v in row.tolist()]
        if not any((str(v).strip() if v is not None else "") for v in vals):
            continue
        rows.append(vals)
    if not rows:
        raise ValueError("Excel(.xls) 文件为空或未读取到有效数据。")
    return rows


def read_tabular_file(file_path, filename: str | None = None) -> list[list]:
    """统一二维读取入口：根据扩展名选择 openpyxl / csv / xls 解析。"""
    ext = get_file_ext(filename or str(file_path))
    if ext == ".csv":
        return read_csv_rows(file_path)
    if ext in WORKBOOK_EXTS:
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if ext == ".xls":
        if not _xls_supported():
            raise ValueError("暂不支持 .xls，请另存为 .xlsx 后上传。")
        return _read_xls_rows(file_path)
    raise ValueError(f"不支持的文件格式：{ext or '未知'}")


# ─── openpyxl 兼容适配器（让 CSV/.xls 复用既有 Sheet 解析逻辑）───
class _TableCell:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class _TableWorksheet:
    """模拟 openpyxl Worksheet：提供 iter_rows / max_row。"""

    def __init__(self, rows: list[list]):
        self._rows = rows
        self.max_row = len(rows)
        self.max_column = max((len(r) for r in rows), default=0)

    def iter_rows(self, min_row: int = 1, max_row: int | None = None,
                  min_col: int | None = None, max_col: int | None = None,
                  values_only: bool = False):
        start = (min_row - 1) if (min_row and min_row > 0) else 0
        end = len(self._rows) if max_row is None else min(max_row, len(self._rows))
        for r in self._rows[start:end]:
            if values_only:
                yield tuple(r)
            else:
                yield [_TableCell(v) for v in r]


class _TableWorkbook:
    """模拟 openpyxl Workbook（单 Sheet），供 CSV/.xls 复用既有解析器。"""

    def __init__(self, rows: list[list]):
        self._ws = _TableWorksheet(rows)
        self.sheetnames = ["Sheet1"]

    @property
    def active(self):
        return self._ws

    def __getitem__(self, name):
        return self._ws

    def close(self):
        pass


def load_table_workbook(file_path, filename: str | None = None):
    """
    统一“工作簿”入口：返回 openpyxl Workbook 或兼容适配器。
    既有 8 类解析器（parse_*_file）无需改动即可解析 CSV / .xls。
    """
    ext = get_file_ext(filename or str(file_path))
    if ext in WORKBOOK_EXTS:
        import openpyxl
        # read_only=True 流式单次读取：几十万行大文件下显著降低内存与耗时；
        # 读完即落地为列表型适配器，供各解析器多次迭代（read_only 工作表本身不支持重复迭代）。
        wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
        try:
            ws = wb.active
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
        return _TableWorkbook(rows)
    if ext == ".csv":
        return _TableWorkbook(read_csv_rows(file_path))
    if ext == ".xls":
        if not _xls_supported():
            raise ValueError("暂不支持 .xls，请另存为 .xlsx 后上传。")
        return _TableWorkbook(_read_xls_rows(file_path))
    raise ValueError(f"不支持的文件格式：{ext or '未知'}")


def humanize_parse_error(err: str | None) -> str:
    """把底层（含 openpyxl 英文）报错转成简短中文，不向前端暴露长堆栈。"""
    if not err:
        return "未知错误"
    s = str(err)
    if "does not support .csv" in s or "Supported formats" in s:
        return "系统未能按 CSV 解析该文件，请确认是标准 CSV，或另存为 .xlsx 后上传"
    if "not a zip file" in s.lower() or "BadZipFile" in s:
        return "文件已损坏或不是有效的 Excel 文件，请重新导出后上传"
    first = s.strip().splitlines()[0]
    return first[:120]

# ─── 正则 ──────────────────────────────────────────────────
_INVISIBLE_RE  = re.compile(r"[　​‌‍﻿\xa0\s]+")
_EXPRESS_NAME_RE = re.compile(
    r"(?:[一-龥A-Za-z]{2,}?(?:快递|速运|物流|邮政|快运)|顺丰|圆通|中通|韵达|申通|百世|极兔|京东|EMS|德邦|天天)"
)
_EXPRESS_NO_RE = re.compile(r"\b([A-Z0-9]{8,})\b")

# ─── 列名别名 ──────────────────────────────────────────────
_ORDER_ALIASES = {
    "main_order_no":       ["主订单号", "主订单编号", "订单号", "外部订单号"],
    "sub_order_no":        ["子订单号", "子订单编号", "子订单"],
    "store_name":          ["店铺名称", "店铺"],
    "order_status":        ["订单状态"],
    "after_sale_status":   ["售后状态"],
    "ship_time":           ["发货时间", "订单发货时间", "实际发货时间", "物流发货时间", "发货完成时间", "发货日期", "出库时间"],
    "order_pay_amount":    ["订单应付金额", "应付金额", "应付款", "实付金额"],
    "item_price":          ["商品单价", "单价"],
    "merchant_discount":   ["商家实际承担优惠金额", "商家实际承担优惠", "商家承担优惠"],
    "price_reduction_discount": ["降价类优惠", "降价优惠"],
    "order_freight":       ["运费", "应收运费", "订单运费"],
    "platform_discount":   ["平台优惠", "平台补贴"],
    "talent_discount":     ["达人优惠", "创作者优惠"],
    "receivable_amount":   ["应收金额", "应收款"],
    "settlement_income":   ["结算金额", "收款金额", "实收金额", "结算收入", "商家收入金额", "商家实收"],
    "refund_amount":       ["退款金额", "退金额"],
    "product_code":        ["商品编码", "商品ID", "编码", "货号"],
    "product_name":        ["商品名称", "商品标题"],
    "sku_name":            ["规格", "SKU", "SKU名称", "商品规格"],
    "quantity":            ["数量", "购买数量"],
    "express_info":        ["快递信息", "物流信息"],
    "express_company":     ["快递公司", "物流公司", "快递"],
    "express_no":          ["快递单号", "物流单号", "运单号"],
    "fund_refund_amount":  ["资金退款", "退款（资金账单）"],
}

_SETTLEMENT_ALIASES = {
    "main_order_no":       ["主订单编号", "主订单号", "订单号"],
    "sub_order_no":        ["子订单号", "子订单编号"],
    "settlement_time":     ["结算时间"],
    "income_total":        ["收入合计", "收入小计", "商家实收金额", "结算收入"],
    "settlement_before_refund": ["结算前退款金额", "结算前退款"],
    "platform_service_fee": ["平台服务费", "服务费", "平台服务费用"],
    "talent_commission":   ["达人佣金", "达人服务费", "创作者佣金"],
}

_AFTER_SALE_ALIASES = {
    "sub_order_no":      ["子订单号", "子订单编号", "退货子订单号", "商品单号", "订单号"],
    "after_sale_status": ["售后状态", "售后类型", "退款原因", "线上状态"],
    "refund_amount":     ["退款金额", "退金额", "应付金额（元）"],
}

# 售后单：子订单编号 / 退商品金额 必须按“别名优先级 + 精确优先”定位，
# 否则会被“内部订单号 / 卖家应退金额”等相邻列误匹配（导致与店铺订单 0 匹配、退款金额=0）。
_AS_SUB_ALIASES = ["子订单编号", "子订单号", "退货子订单号", "线上订单号", "线上单号"]
_AS_SUB_EXCLUDE = ("内部", "原始", "原订单", "售后单号", "退款编码", "退回快递")
_AS_REFUND_ALIASES = ["退商品金额", "退款金额", "退金额", "卖家应退金额", "应付金额（元）"]

_PRODUCT_COST_ALIASES = {
    "product_code": ["商品编码", "货号", "编码", "商品ID"],
    "cost_price":   ["成本价", "采购价", "商品成本价", "成本"],
}

_SHIPPING_ORDER_ALIASES = {
    "ship_date":        ["发货日期", "发货时间", "出库日期", "出库时间"],
    "product_code":     ["商品编码", "商家编码", "SKU编码", "货号", "编码", "商品ID"],
    "shipped_quantity": ["数量", "发货数量"],
    "returned_quantity": ["实退数量", "实际退货数量", "退货数量"],
}

# 注册表：file_type → parser function
PARSER_REGISTRY: dict[str, Any] = {}


# ─── 工具函数 ──────────────────────────────────────────────

def _clean_no(v) -> str:
    """订单号 / 商品编码清洗：去除空格、全角空格、换行、制表符、不可见字符。"""
    if v is None:
        return ""
    s = str(v).strip().lstrip("'")
    return _INVISIBLE_RE.sub("", s)


def _strip_header(s: str) -> str:
    return s.replace(" ", "").replace("　", "").replace("\n", "").strip("'`\"")


def _cell(row, col: int):
    # col=-1 表示"未找到"，直接返回空；避免 Python 负索引取到最后一列
    if col < 0:
        return ""
    try:
        v = row[col].value
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        return v
    except Exception:
        return ""


def _to_decimal(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    s = str(v).replace(",", "").replace("¥", "").replace("￥", "").strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


# ─── 金额安全解析 ──────────────────────────────────────────
# 单店单月金额字段安全阈值（防止把编号识别成金额）
MAX_MONEY_ABS = Decimal("10000000")          # 1千万：关键费用字段硬阈值
_ID_LIKE_BOUND = Decimal("100000000000000")  # 1e14：纯编号注入兜底阈值
# 编号类列关键词（这些列绝不能当金额列）
_ID_COLUMN_KEYWORDS = (
    "订单号", "主订单", "子订单", "运单号", "快递单号", "保单号", "流水号",
    "交易号", "支付单号", "编号", "单号", "ID", "Id", "id",
)


class MoneyParseError(ValueError):
    """金额字段疑似被编号污染时抛出。"""
    pass


def _is_id_like(s: str) -> bool:
    """纯数字、长度 >= 12、且无小数点 → 判定为编号而非金额。"""
    core = s[1:] if s.startswith("-") else s
    return core.isdigit() and len(core) >= 12


def parse_money(value, field_name=None, column_name=None, context=None,
                raise_on_anomaly: bool = True):
    """
    统一金额解析：清洗货币符号/逗号/括号负数；拒绝长编号与超阈值。
    raise_on_anomaly=True 时遇到编号/超阈值抛 MoneyParseError；False 时返回 None。
    """
    if column_name and any(k in str(column_name) for k in _ID_COLUMN_KEYWORDS):
        if raise_on_anomaly:
            raise MoneyParseError(
                f"金额字段异常，字段 {field_name}，列 {column_name}，值 {value}，疑似将编号列识别为金额。"
            )
        return None
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, bool):
        return Decimal("0")
    if isinstance(value, (int, float)):
        d = _to_decimal(value)
    else:
        s = str(value).strip()
        if not s:
            return Decimal("0")
        neg = False
        if s.startswith("(") and s.endswith(")"):
            neg, s = True, s[1:-1]
        s = s.replace(",", "").replace("¥", "").replace("￥", "").replace(" ", "").strip()
        if _is_id_like(s):
            if raise_on_anomaly:
                raise MoneyParseError(
                    f"金额字段异常，字段 {field_name}，列 {column_name}，值 {value}，疑似将编号识别为金额。"
                )
            return None
        try:
            d = Decimal(s)
        except (InvalidOperation, ValueError):
            return Decimal("0")
        if neg:
            d = -d
    if d.copy_abs() > MAX_MONEY_ABS:
        if raise_on_anomaly:
            raise MoneyParseError(
                f"金额字段异常，字段 {field_name}，列 {column_name}，值 {value}，超过单字段安全阈值 {MAX_MONEY_ABS}，疑似将编号识别为金额。"
            )
        return None
    return d


def _coerce_money_cell(v):
    """逐行金额取值：空/非数字/长编号/超阈值 → None（跳过），否则 Decimal。"""
    return parse_money(v, raise_on_anomaly=False)


def _to_int(v) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


# 发货时间表头别名（按优先级；包含匹配；排除付款/下单/售后等时间列）
_SHIP_TIME_ALIASES = [
    "发货时间", "订单发货时间", "实际发货时间", "物流发货时间",
    "发货完成时间", "发货日期", "出库时间",
]
_SHIP_TIME_EXCLUDE = ("付款", "下单", "支付", "售后", "创建", "退款", "签收", "成交")

# 发货时间解析格式（dateutil 缺失时回退，覆盖斜杠/单数字月日）
_SHIP_TIME_FORMATS = (
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d",
    "%Y%m%d",
)


def parse_ship_time(value) -> datetime | None:
    """
    统一发货时间解析：支持 datetime/date、Excel 日期序列号、以及多种字符串格式
    （2026/4/10、2026/04/10、2026/4/10 0:00、2026-4-10、2026年4月10日、2026.4.10 等）。
    解析失败返回 None。
    """
    from datetime import date as _date, timedelta as _td
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, _date):
        return datetime(value.year, value.month, value.day)
    # Excel 日期序列号（1899-12-30 起算）
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if 1 <= float(value) <= 600000:
                return datetime(1899, 12, 30) + _td(days=float(value))
        except Exception:
            return None
        return None

    s = str(value).strip()
    if not s:
        return None
    # 归一化中文年月日与全角/不可见空格
    s = _INVISIBLE_RE.sub(" ", s).strip()
    s = s.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    s = re.sub(r"\s+", " ", s).strip().rstrip("-")

    # 优先 dateutil（若已安装），否则多格式 strptime 回退
    try:
        from dateutil.parser import parse as dtparse
        return dtparse(s)
    except Exception:
        pass
    for fmt in _SHIP_TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _to_datetime(v) -> datetime | None:
    # 统一走 parse_ship_time，保证斜杠/中文日期等格式一致解析
    return parse_ship_time(v)


def _find_ship_time_col(headers: list[str]) -> tuple[int, str]:
    """按别名优先级 + 包含匹配定位发货时间列；返回 (列索引, 表头名)，找不到 (-1, '')。"""
    cleaned = [_strip_header(str(h or "")) for h in headers]
    # 1) 精确等于优先
    for alias in _SHIP_TIME_ALIASES:
        for i, h in enumerate(cleaned):
            if h == alias:
                return i, str(headers[i])
    # 2) 包含匹配（排除付款/下单/售后等时间列）
    for alias in _SHIP_TIME_ALIASES:
        for i, h in enumerate(cleaned):
            if alias in h and not any(x in h for x in _SHIP_TIME_EXCLUDE):
                return i, str(headers[i])
    return -1, ""


def _find_header(ws, scan: int = 15, required_keywords: list[str] | None = None) -> int:
    """前 scan 行内找包含所有 required_keywords 的表头行下标；找不到返回 0。"""
    if not required_keywords:
        return 0
    for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=scan)):
        row_text = " ".join(str(c.value or "").strip() for c in row if c.value)
        if all(kw in row_text for kw in required_keywords):
            return ri
    return 0


def _iter_rows(ws, header_row: int):
    """返回 header_row 之后的数据行（openpyxl row tuples）。"""
    rows = list(ws.iter_rows())
    for row in rows[header_row + 1:]:
        yield row


def _resolve_columns(headers: list[str], col_aliases: dict) -> dict[str, int]:
    """
    按关键字模糊匹配表头列下标。返回 {字段: 列索引}（找不到的字段不出现）
    """
    result = {}
    for field, aliases in col_aliases.items():
        for ci, h in enumerate(headers):
            h_clean = _strip_header(h)
            for alias in aliases:
                if alias in h_clean or h_clean in alias:
                    result[field] = ci
                    break
            if field in result:
                break
    return result


def _find_col_priority(headers: list[str], aliases: list[str], exclude: tuple = ()) -> int:
    """
    按别名优先级 + 精确优先定位列：先找精确等于的表头，再按别名顺序找包含匹配。
    避免“别名靠后但列在前”被相邻列误抢（如 内部订单号 / 卖家应退金额）。
    返回列下标，找不到返回 -1。
    """
    cleaned = [_strip_header(str(h or "")) for h in headers]
    for alias in aliases:                       # 1) 精确等于（按别名优先级）
        for i, h in enumerate(cleaned):
            if h == alias and not any(x in h for x in exclude):
                return i
    for alias in aliases:                       # 2) 包含匹配（按别名优先级）
        for i, h in enumerate(cleaned):
            if alias in h and not any(x in h for x in exclude):
                return i
    return -1


def _parse_amount_total(ws) -> Decimal:
    """资金账单：本期只统计总金额，后续按字段类型归集。"""
    total = Decimal("0")
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, (int, float)) and v != 0:
                total += _to_decimal(v)
                return total
            if isinstance(v, str):
                s = v.replace(",", "").replace("¥", "").replace("￥", "").strip()
                try:
                    total += Decimal(s)
                    return total
                except Exception:
                    pass
    return total


def _split_express_info(v: str) -> tuple[str, str]:
    """按业务文档从“快递信息”拆出 (快递公司, 快递单号)。"""
    if not v:
        return "", ""
    first = str(v).split(",", 1)[0].split("，", 1)[0].strip()
    if "-" not in first:
        return "", _clean_no(first)
    express_no, company_part = first.split("-", 1)
    chinese = "".join(re.findall(r"[一-龥]", company_part))
    company = chinese[:2] if chinese else company_part.strip()[:2]
    return company, _clean_no(express_no)


# ─── 解析器：订单文件 ─────────────────────────────────────

def _month_range(month: str) -> tuple[datetime, datetime]:
    """'2026-04' → (2026-04-01 00:00:00, 2026-05-01 00:00:00)。"""
    y, m = month.split("-")[:2]
    y, m = int(y), int(m)
    start = datetime(y, m, 1)
    end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    return start, end


def parse_order_file(wb, month: str, store_name: str, diag: dict | None = None) -> list[dict]:
    """
    店铺订单解析；按发货时间过滤当月数据。
    diag: 可选 dict，函数会写入诊断信息（表头列名/解析成功失败数/当月命中数/最小最大发货时间等）。
    """
    ws = wb.active
    # 先扫表头
    header_row_idx = _find_header(ws, scan=15, required_keywords=["订单"])
    rows_iter = list(ws.iter_rows())
    if not rows_iter:
        raise ValueError("空文件")

    header_row = rows_iter[header_row_idx]
    headers = [str(c.value or "").strip() for c in header_row]
    cols = _resolve_columns(headers, _ORDER_ALIASES)

    if "sub_order_no" not in cols and "main_order_no" not in cols:
        raise ValueError("表头未找到主订单/子订单编号列")

    # 商品编码用于匹配《商品成本表》：抖音订单的“商品ID”是平台ID，无法匹配成本表 SKU；
    # 优先用“商家编码/货号”（商家 SKU，与成本表商品编码一致），匹配不到再退回原列。
    pcode_idx = _find_col_priority(
        headers, ["商家编码", "商品编码", "货号", "商家SKU", "商品ID", "编码"],
        exclude=("订单", "运单", "快递"),
    )
    if pcode_idx >= 0:
        cols["product_code"] = pcode_idx

    # 发货时间列：专用优先级匹配（比通用 _resolve_columns 更稳）
    ship_idx, ship_col_name = _find_ship_time_col(headers)
    if ship_idx < 0:
        raise ValueError("表头未找到发货时间列，无法按销售月报月份筛选订单")

    # 月份区间（datetime 比较，避免字符串/前缀比较踩坑）
    m_start, m_end = _month_range(month)

    # 诊断统计
    total_rows = 0
    parse_ok = 0
    parse_fail = 0
    blank_ship_time = 0
    in_month = 0
    failed_samples: list[str] = []
    min_dt: datetime | None = None
    max_dt: datetime | None = None

    results = []
    errors = []
    for ri, row in enumerate(rows_iter[header_row_idx + 1:], start=header_row_idx + 2):
        sub_no   = _clean_no(_cell(row, cols.get("sub_order_no", -1)))
        main_no  = _clean_no(_cell(row, cols.get("main_order_no", -1)))
        if not sub_no and not main_no:
            continue
        total_rows += 1

        # 发货时间 → 解析；空白保留（=不结算），其他月份丢弃
        ship_raw = _cell(row, ship_idx) if ship_idx >= 0 else None
        ship_dt  = parse_ship_time(ship_raw)
        if ship_dt is not None:
            parse_ok += 1
            if min_dt is None or ship_dt < min_dt:
                min_dt = ship_dt
            if max_dt is None or ship_dt > max_dt:
                max_dt = ship_dt
            if not (m_start <= ship_dt < m_end):
                continue   # 确认是其他月份 → 丢弃
            in_month += 1
        else:
            if ship_raw not in (None, ""):
                parse_fail += 1
                if len(failed_samples) < 5:
                    failed_samples.append(str(ship_raw)[:40])
                # 非空但无法解析的日期不是“发货时间空白”，不能误判为不结算。
                continue
            # 真正空白的发货时间才保留，后续按现有规则判定为「不结算」。
            blank_ship_time += 1

        # 快递信息
        express_co = ""
        express_no = ""
        if "express_info" in cols:
            express_co, express_no = _split_express_info(str(_cell(row, cols["express_info"])))
        if not express_co and "express_company" in cols:
            express_co = str(_cell(row, cols["express_company"]))
        if not express_no and "express_no" in cols:
            express_no = _clean_no(_cell(row, cols["express_no"]))

        qty       = _to_int(_cell(row, cols.get("quantity", -1)))
        item_price = _to_decimal(_cell(row, cols.get("item_price", -1)))
        merch_disc = _to_decimal(_cell(row, cols.get("merchant_discount", -1)))
        ord_freight = _to_decimal(_cell(row, cols.get("order_freight", -1)))
        price_reduction = _to_decimal(_cell(row, cols.get("price_reduction_discount", -1)))
        # 新版应收金额 = 商品单价 × 商品数量 - 商家实际承担优惠金额 + 运费
        receivable = item_price * Decimal(qty) - merch_disc + ord_freight
        product_amount = receivable + price_reduction

        d = {
            "store_name":          store_name,
            "main_order_no":       main_no or sub_no,
            "sub_order_no":        sub_no,
            "product_code":        _clean_no(_cell(row, cols.get("product_code", -1))),
            "product_name":        str(_cell(row, cols.get("product_name", -1))),
            "sku_name":            str(_cell(row, cols.get("sku_name", -1))),
            "quantity":            qty,
            "ship_time":           ship_dt,
            "order_status":        str(_cell(row, cols.get("order_status", -1))),
            "after_sale_status":   str(_cell(row, cols.get("after_sale_status", -1))) or "-",
            "order_pay_amount":    _to_decimal(_cell(row, cols.get("order_pay_amount", -1))),
            "item_price":          item_price,
            "merchant_discount":   merch_disc,
            "order_freight":       ord_freight,
            "price_reduction_discount": price_reduction,
            "product_amount":      product_amount,
            "platform_discount":   _to_decimal(_cell(row, cols.get("platform_discount", -1))),
            "talent_discount":     _to_decimal(_cell(row, cols.get("talent_discount", -1))),
            "receivable_amount":   receivable,
            "settlement_income":   Decimal("0"),   # 由结算账单收入合计>0 回填
            "settlement_amount_total": Decimal("0"),
            "settlement_difference": product_amount,
            "refund_amount":       Decimal("0"),   # 由结算账单收入合计<0 回填
            "fund_refund_amount":  Decimal("0"),
            "platform_service_fee": Decimal("0"),
            "talent_commission":   Decimal("0"),
            "express_company":     express_co,
            "express_no":          express_no,
        }
        results.append(d)

    if diag is not None:
        diag.update({
            "total_rows": total_rows,
            "ship_time_column_found": ship_idx >= 0,
            "ship_time_column_name": ship_col_name or None,
            "ship_time_parse_success_count": parse_ok,
            "ship_time_parse_failed_count": parse_fail,
            "ship_time_blank_count": blank_ship_time,
            "rows_in_selected_month": in_month,
            "selected_month": month,
            "min_ship_time": min_dt.strftime("%Y-%m-%d %H:%M:%S") if min_dt else None,
            "max_ship_time": max_dt.strftime("%Y-%m-%d %H:%M:%S") if max_dt else None,
            "parse_failed_samples": failed_samples,
        })
        if not ship_idx >= 0:
            diag["message"] = "订单表未识别到发货时间列，请检查表头是否包含“发货时间”"
        elif in_month == 0:
            diag["message"] = (
                f"订单表已识别发货时间列「{ship_col_name}」，但没有筛选到 {month} 月内订单"
            )
        else:
            diag["message"] = f"已筛选到 {in_month} 笔 {month} 月内订单"

    return results


# ─── 解析器：结算账单 ─────────────────────────────────────

def parse_settlement_file(wb, month: str, diag: dict | None = None,
                          label_amount_map: dict[tuple[str, str], Decimal] | None = None
                          ) -> dict[tuple[str, str], dict]:
    """
    按结算时间筛选当月，以主订单编号+子订单编号联合汇总。
    label_amount_map 另行汇总文件内全部日期的收入合计，仅供订单标签判定。
    收入合计>0 → 收款金额(settlement_income)；收入合计<0 → 退款/退货金额(refund_amount，取绝对值)。
    返回 {(main_order_no, sub_order_no): {...}}。
    """
    ws = wb.active
    header_row_idx = _find_header(ws, scan=15, required_keywords=["子订单"])
    rows_iter = list(ws.iter_rows())
    if not rows_iter:
        return {}
    header_row = rows_iter[header_row_idx]
    headers = [str(c.value or "").strip() for c in header_row]
    cols = _resolve_columns(headers, _SETTLEMENT_ALIASES)
    main_idx = _find_col_priority(headers, ["主订单编号", "主订单号", "订单号"], exclude=("子",))
    sub_idx = _find_col_priority(headers, ["子订单编号", "子订单号"])
    if main_idx >= 0:
        cols["main_order_no"] = main_idx
    if sub_idx >= 0:
        cols["sub_order_no"] = sub_idx

    required = ("main_order_no", "sub_order_no", "settlement_time", "income_total")
    missing = [name for name in required if name not in cols]
    if missing:
        raise ValueError(f"结算账单缺少必需字段：{'、'.join(missing)}")

    m_start, m_end = _month_range(month)
    result: dict[tuple[str, str], dict] = {}
    total_rows = rows_in_month = date_parse_failed = 0
    raw_platform_fee = raw_talent_commission = Decimal("0")
    raw_payment = raw_refund = Decimal("0")
    for row in rows_iter[header_row_idx + 1:]:
        total_rows += 1
        settlement_time = parse_ship_time(_cell(row, cols["settlement_time"]))
        if settlement_time is None:
            date_parse_failed += 1
            continue
        main_no = _clean_no(_cell(row, cols["main_order_no"]))
        sub_no = _clean_no(_cell(row, cols["sub_order_no"]))
        if not main_no or not sub_no:
            continue
        inc = _to_decimal(_cell(row, cols.get("income_total", -1)))
        key = (main_no, sub_no)
        if label_amount_map is not None:
            label_amount_map[key] = label_amount_map.get(key, Decimal("0")) + inc
        if not (m_start <= settlement_time < m_end):
            continue
        rows_in_month += 1
        before = _to_decimal(_cell(row, cols.get("settlement_before_refund", -1)))
        commission = _to_decimal(_cell(row, cols.get("talent_commission", -1)))
        platform_fee = _to_decimal(_cell(row, cols.get("platform_service_fee", -1)))
        rec = result.get(key)
        if rec is None:
            rec = {"settlement_amount_total": Decimal("0"), "settlement_income": Decimal("0"),
                   "refund_amount": Decimal("0"), "settlement_before_refund": Decimal("0"),
                   "platform_service_fee": Decimal("0"), "talent_commission": Decimal("0")}
            result[key] = rec
        rec["settlement_amount_total"] += inc
        if inc > 0:
            rec["settlement_income"] += inc
            raw_payment += inc
        elif inc < 0:
            rec["refund_amount"] += (-inc)   # 退货金额取绝对值
            raw_refund += (-inc)
        rec["settlement_before_refund"] += before
        rec["platform_service_fee"] += platform_fee
        rec["talent_commission"] += commission
        raw_platform_fee += platform_fee
        raw_talent_commission += commission
    if diag is not None:
        diag.update({
            "total_rows": total_rows, "rows_in_month": rows_in_month,
            "date_parse_failed_count": date_parse_failed, "settlement_time_column": headers[cols["settlement_time"]],
            "matched_key_count": len(result), "platform_service_fee_total": raw_platform_fee,
            "talent_commission_total": raw_talent_commission,
            "payment_total": raw_payment, "refund_total": raw_refund,
            "filter": f"{m_start:%Y-%m-%d %H:%M:%S} <= 结算时间 < {m_end:%Y-%m-%d %H:%M:%S}",
        })
    return result


# ─── 解析器：售后单 ───────────────────────────────────────

def parse_after_sale_file(wb) -> dict[str, dict]:
    """返回 {sub_order_no: {after_sale_status, refund_amount}}"""
    ws = wb.active
    header_row_idx = _find_header(ws, scan=15, required_keywords=["子订单"])
    rows_iter = list(ws.iter_rows())
    if not rows_iter:
        return {}
    header_row = rows_iter[header_row_idx]
    headers = [str(c.value or "").strip() for c in header_row]
    cols = _resolve_columns(headers, _AFTER_SALE_ALIASES)

    # 子订单编号 / 退商品金额 用别名优先级定位（避免被 内部订单号 / 卖家应退金额 误抢）
    sub_idx    = _find_col_priority(headers, _AS_SUB_ALIASES, _AS_SUB_EXCLUDE)
    refund_idx = _find_col_priority(headers, _AS_REFUND_ALIASES)
    if sub_idx < 0:
        sub_idx = cols.get("sub_order_no", -1)
    if refund_idx < 0:
        refund_idx = cols.get("refund_amount", -1)
    if sub_idx < 0:
        raise ValueError("表头未找到子订单编号列")

    status_idx = cols.get("after_sale_status", -1)

    result = {}
    for row in rows_iter[header_row_idx + 1:]:
        sub_no = _clean_no(_cell(row, sub_idx))
        if not sub_no:
            continue
        result[sub_no] = {
            "after_sale_status": str(_cell(row, status_idx)),
            "refund_amount": _to_decimal(_cell(row, refund_idx)),
        }
    return result


# ─── 金额型文件（运费/运费险/广告费/资金）按金额列汇总 ──────
_AMOUNT_KEYWORDS = {
    "freight_insurance": ["运费险金额", "退货运费险金额", "运费险保费", "保险费", "保费",
                          "扣费金额", "运费险", "服务费", "金额", "费用"],
    "freight":           ["运费金额", "快递费", "物流费", "运费", "金额", "费用"],
    "ad_cost":           ["广告费", "推广费", "广告消耗", "消耗", "投放金额", "花费", "金额", "费用"],
    "fund":              ["收入合计", "金额", "实收", "流水金额", "收入", "支出"],
}
_AMOUNT_FILE_LABEL = {"freight_insurance": "运费险", "freight": "运费", "ad_cost": "广告费", "fund": "资金账单"}
_AMOUNT_HINT = {
    "freight_insurance": "运费险金额/保费/保险费/扣费金额",
    "freight": "运费金额/快递费/物流费",
    "ad_cost": "广告费/推广费/消耗/花费",
    "fund": "金额/收入合计",
}


def parse_amount_file(wb, file_type: str, diag: dict | None = None) -> Decimal:
    """
    金额型文件（运费/运费险/广告费/资金）按表头定位金额列后逐行汇总。
    - 排除编号类列（订单号/保单号/运单号/编号…），绝不把长编号当金额。
    - 找不到金额列直接报错，不随机取第一列数字。
    """
    ws = wb.active
    rows = list(ws.iter_rows())
    label = _AMOUNT_FILE_LABEL.get(file_type, file_type)
    if not rows:
        if diag is not None:
            diag.update({"amount_column": None, "rows": 0, "method": "empty"})
        return Decimal("0")

    kws = _AMOUNT_KEYWORDS.get(file_type, ["金额", "费用"])
    # 在前 15 行里找“真正的表头行”：能定位到金额列、且非空单元格最多的一行
    # （避免合并标题行如「快递运单费用」误当表头，导致汇总到“序号”列）
    header_idx, col_idx, col_name = -1, -1, None
    best_nonempty = -1
    for ri in range(min(15, len(rows))):
        headers = [str(c.value or "").strip() for c in rows[ri]]
        nonempty = sum(1 for h in headers if h)
        ci = _find_col_priority(headers, kws, exclude=_ID_COLUMN_KEYWORDS)
        if ci >= 0 and nonempty > best_nonempty:
            best_nonempty = nonempty
            header_idx, col_idx, col_name = ri, ci, headers[ci]

    if col_idx < 0:
        raise ValueError(
            f"{label}表未识别到有效金额列，请检查是否包含“{_AMOUNT_HINT.get(file_type, '金额')}”等字段。"
        )

    total = Decimal("0")
    used = 0
    skipped = 0
    for row in rows[header_idx + 1:]:
        d = _coerce_money_cell(_cell(row, col_idx))
        if d is None:
            if _cell(row, col_idx) not in (None, ""):
                skipped += 1
            continue
        total += d
        used += 1

    if diag is not None:
        diag.update({
            "amount_column": col_name, "header_row": header_idx + 1,
            "rows": used, "skipped": skipped, "total": total, "method": "by_column",
            "rule": f"按表头定位金额列「{col_name}」逐行汇总，排除编号类列与超阈值/长编号值",
        })
    return total


# ─── 解析器：资金账单（新版：按动账场景/动账时间归集）──────
# 平台其他费用归集的动账场景
_FUND_OTHER_FEE_SCENES = ("偏远地区物流服务", "权益保险", "上门取件运费")


def parse_fund_aggregates(wb, month: str, diag: dict | None = None) -> dict:
    """
    新版资金账单：按“动账时间”筛选当月，按“动账场景”归集店铺级费用。
    返回 dict：platform_service_fee / consumer_compensation / small_payment /
    freight_insurance / freight_insurance_by_sub / platform_other_fee / settlement_after_refund
    及 scene_breakdown（各场景动账金额合计，供日志）。
    """
    ws = wb.active
    rows = list(ws.iter_rows())
    out = {
        "platform_service_fee": Decimal("0"),
        "consumer_compensation": Decimal("0"),
        "small_payment": Decimal("0"),
        "freight_insurance": Decimal("0"),
        "freight_insurance_by_sub": {},
        "freight_insurance_without_sub_amount": Decimal("0"),
        "freight_insurance_with_sub_count": 0,
        "freight_insurance_without_sub_count": 0,
        "fund_refund_by_sub": {},
        "fund_refund_with_sub_count": 0,
        "fund_refund_without_sub_count": 0,
        "platform_other_fee": Decimal("0"),
        "settlement_after_refund": Decimal("0"),
        "scene_breakdown": {},
        "rows_in_month": 0,
    }
    if not rows:
        return out
    headers = [str(c.value or "").strip() for c in rows[0]]
    i_time  = _find_col_priority(headers, ["动账时间", "动帐时间"])
    i_amt   = _find_col_priority(headers, ["动账金额", "动帐金额"], exclude=("方向", "账户"))
    i_scene = _find_col_priority(headers, ["动账场景", "动帐场景"])
    i_psf   = _find_col_priority(headers, ["平台服务费"])
    i_sub   = _find_col_priority(headers, ["子订单编号", "子订单号"])
    if i_time < 0 or i_scene < 0 or i_amt < 0:
        raise ValueError("资金账单未识别到动账时间/动账场景/动账金额列")

    m_start, m_end = _month_range(month)
    from collections import Counter
    scenes: Counter = Counter()
    for row in rows[1:]:
        dt = parse_ship_time(_cell(row, i_time))
        if dt is None or not (m_start <= dt < m_end):
            continue
        out["rows_in_month"] += 1
        amt = _coerce_money_cell(_cell(row, i_amt)) or Decimal("0")
        scene = str(_cell(row, i_scene) or "").strip()
        scenes[scene] += float(amt)
        if i_psf >= 0:
            out["platform_service_fee"] += (_coerce_money_cell(_cell(row, i_psf)) or Decimal("0"))
        if "消费者赔付" in scene:
            out["consumer_compensation"] += amt
        elif "小额打款" in scene:
            out["small_payment"] += amt
        elif "运费险" in scene:
            out["freight_insurance"] += amt
            sub_no = _clean_no(_cell(row, i_sub)) if i_sub >= 0 else ""
            if sub_no:
                by_sub = out["freight_insurance_by_sub"]
                by_sub[sub_no] = by_sub.get(sub_no, Decimal("0")) + amt
                out["freight_insurance_with_sub_count"] += 1
            else:
                out["freight_insurance_without_sub_amount"] += amt
                out["freight_insurance_without_sub_count"] += 1
        elif any(name in scene for name in _FUND_OTHER_FEE_SCENES):
            out["platform_other_fee"] += amt
        elif "结算后退款" in scene:
            out["settlement_after_refund"] += amt
            sub_no = _clean_no(_cell(row, i_sub)) if i_sub >= 0 else ""
            if sub_no:
                by_sub = out["fund_refund_by_sub"]
                by_sub[sub_no] = by_sub.get(sub_no, Decimal("0")) + amt
                out["fund_refund_with_sub_count"] += 1
            else:
                out["fund_refund_without_sub_count"] += 1
    out["scene_breakdown"] = {k: round(v, 2) for k, v in scenes.most_common(20)}
    if diag is not None:
        diag.update({k: (str(v) if isinstance(v, Decimal) else v) for k, v in out.items()})
    return out


# ─── 解析器：运费（新版：按运单号/子订单匹配）──────────────
def parse_freight_by_waybill(wb, diag: dict | None = None) -> dict:
    """
    新版运费表：优先按子订单号匹配，否则按快递单号(运单号)匹配。
    返回 {"by_sub": {sub: fee}, "by_waybill": {waybill: fee}, "total": Decimal}
    （月报运费 = 与本月订单匹配上的运费之和，在 service 层按订单 express_no/sub 匹配）
    """
    ws = wb.active
    rows = list(ws.iter_rows())
    res = {"by_sub": {}, "by_waybill": {}, "total": Decimal("0"), "amount_column": None, "rows": 0}
    if not rows:
        return res
    # 找真正表头行（跳过合并标题行）
    header_idx, hdr = -1, []
    best = -1
    fee_kws = ["应付金额", "运费金额", "快递费", "费用(元)", "费用", "运费", "金额"]
    for ri in range(min(15, len(rows))):
        hs = [str(c.value or "").strip() for c in rows[ri]]
        ne = sum(1 for h in hs if h)
        if _find_col_priority(hs, fee_kws, exclude=_ID_COLUMN_KEYWORDS) >= 0 and ne > best:
            best, header_idx, hdr = ne, ri, hs
    if header_idx < 0:
        raise ValueError("运费表未识别到金额列，请检查是否包含“应付金额/运费金额/快递费/费用(元)”等字段")
    fee_idx = _find_col_priority(hdr, fee_kws, exclude=_ID_COLUMN_KEYWORDS)
    sub_idx = _find_col_priority(hdr, ["子订单号", "子订单编号"])
    way_idx = _find_col_priority(hdr, ["运单号码", "运单号", "快递单号", "物流单号"])
    total = Decimal("0")
    used = 0
    for row in rows[header_idx + 1:]:
        fee = _coerce_money_cell(_cell(row, fee_idx))
        if fee is None:
            continue
        total += fee
        used += 1
        if sub_idx >= 0:
            sub = _clean_no(_cell(row, sub_idx))
            if sub:
                res["by_sub"][sub] = res["by_sub"].get(sub, Decimal("0")) + fee
        if way_idx >= 0:
            way = _clean_no(_cell(row, way_idx))
            if way:
                res["by_waybill"][way] = res["by_waybill"].get(way, Decimal("0")) + fee
    res["total"] = total
    res["amount_column"] = hdr[fee_idx]
    res["rows"] = used
    res["has_sub"] = sub_idx >= 0
    res["has_waybill"] = way_idx >= 0
    if diag is not None:
        diag.update({"amount_column": hdr[fee_idx], "rows": used, "total": str(total),
                     "match_by": ("子订单号" if sub_idx >= 0 else ("运单号" if way_idx >= 0 else "无匹配键-取总额")),
                     "by_sub_keys": len(res["by_sub"]), "by_waybill_keys": len(res["by_waybill"])})
    return res


def parse_fund_file(wb) -> Decimal:
    """旧入口（兼容工作簿 Sheet 校验）：返回当月动账金额总额近似值。"""
    return parse_amount_file(wb, "fund")


# ─── 解析器：运费（旧总额入口，保留兼容）──────────────────

def parse_freight_file(wb) -> Decimal:
    return parse_amount_file(wb, "freight")


# ─── 解析器：运费险 ───────────────────────────────────────

def parse_freight_insurance_file(wb) -> Decimal:
    return parse_amount_file(wb, "freight_insurance")


# ─── 解析器：广告费 ───────────────────────────────────────

def parse_ad_cost_file(wb) -> Decimal:
    return parse_amount_file(wb, "ad_cost")


# ─── 解析器：商品成本表 ───────────────────────────────────

# 发货订单：按发货日期筛选并按商品编码汇总实发数量
def parse_shipping_order_file(wb, month: str, diag: dict | None = None) -> dict[str, dict]:
    """按发货日期筛选当月，返回按商品编码汇总的发货/实退/实发数量。"""
    ws = wb.active
    rows = list(ws.iter_rows())
    if not rows:
        raise ValueError("发货订单为空")

    header_idx = -1
    headers: list[str] = []
    cols: dict[str, int] = {}
    required = ("ship_date", "product_code", "shipped_quantity", "returned_quantity")
    best_resolved: dict[str, int] = {}
    for ri in range(min(15, len(rows))):
        candidate = [str(c.value or "").strip() for c in rows[ri]]
        resolved = {
            "ship_date": _find_col_priority(candidate, _SHIPPING_ORDER_ALIASES["ship_date"]),
            "product_code": _find_col_priority(candidate, _SHIPPING_ORDER_ALIASES["product_code"],
                                                 exclude=("订单", "主", "子")),
            "shipped_quantity": _find_col_priority(candidate, ["发货数量", "数量"],
                                                     exclude=("实退", "退货", "退款")),
            "returned_quantity": _find_col_priority(candidate, _SHIPPING_ORDER_ALIASES["returned_quantity"]),
        }
        resolved = {key: idx for key, idx in resolved.items() if idx >= 0}
        if len(resolved) > len(best_resolved):
            best_resolved = resolved
        if all(key in resolved for key in required):
            header_idx, headers, cols = ri, candidate, resolved
            break
    if header_idx < 0:
        missing_cn = {
            "ship_date": "发货日期", "product_code": "商品编码",
            "shipped_quantity": "数量", "returned_quantity": "实退数量",
        }
        missing = [missing_cn[key] for key in required if key not in best_resolved]
        raise ValueError(f"发货订单缺少必需字段：{'、'.join(missing)}")

    m_start, m_end = _month_range(month)
    result: dict[str, dict] = {}
    total_rows = rows_in_month = date_parse_failed = 0
    shipped_total = returned_total = Decimal("0")

    for row in rows[header_idx + 1:]:
        if not any(_cell(row, i) not in (None, "") for i in range(len(headers))):
            continue
        total_rows += 1
        ship_date = parse_ship_time(_cell(row, cols["ship_date"]))
        if ship_date is None:
            date_parse_failed += 1
            continue
        if not (m_start <= ship_date < m_end):
            continue
        rows_in_month += 1
        product_code = _clean_no(_cell(row, cols["product_code"]))
        if not product_code:
            continue
        shipped_qty = _to_decimal(_cell(row, cols["shipped_quantity"]))
        returned_qty = _to_decimal(_cell(row, cols["returned_quantity"]))
        rec = result.setdefault(product_code, {
            "shipped_quantity": Decimal("0"),
            "returned_quantity": Decimal("0"),
            "net_shipped_quantity": Decimal("0"),
        })
        rec["shipped_quantity"] += shipped_qty
        rec["returned_quantity"] += returned_qty
        shipped_total += shipped_qty
        returned_total += returned_qty

    for rec in result.values():
        rec["net_shipped_quantity"] = rec["shipped_quantity"] - rec["returned_quantity"]

    if diag is not None:
        diag.update({
            "ship_date_column": headers[cols["ship_date"]],
            "month": month,
            "filter": f"{m_start:%Y-%m-%d %H:%M:%S} <= 发货日期 < {m_end:%Y-%m-%d %H:%M:%S}",
            "total_rows": total_rows,
            "rows_in_month": rows_in_month,
            "date_parse_failed_count": date_parse_failed,
            "product_code_count": len(result),
            "shipped_quantity_total": shipped_total,
            "returned_quantity_total": returned_total,
            "net_shipped_quantity_total": shipped_total - returned_total,
            "formula": "按商品编码汇总：实发数量 = 数量 - 实退数量",
        })
    return result


# 商品成本表：商品编码 -> 成本价
def parse_product_cost_file(wb) -> dict[str, Decimal]:
    """返回 {product_code: cost_price}"""
    ws = wb.active
    header_row_idx = _find_header(ws, scan=15, required_keywords=["编码", "成本"])
    rows_iter = list(ws.iter_rows())
    if not rows_iter:
        return {}
    if header_row_idx >= len(rows_iter):
        raise ValueError("表头未找到商品编码或成本价列")
    header_row = rows_iter[header_row_idx]
    headers = [str(c.value or "").strip() for c in header_row]
    cols = _resolve_columns(headers, _PRODUCT_COST_ALIASES)

    # 商品编码优先用“商品编码/商家编码”精确列（与订单商家编码同口径）；
    # 款式编码作为补充键，二者都建索引以最大化匹配率。
    sp_idx = _find_col_priority(headers, ["商品编码", "商家编码", "货号", "SKU编码", "SKU"],
                                exclude=("款式", "订单", "主", "子"))
    ks_idx = _find_col_priority(headers, ["款式编码", "款号"], exclude=("订单",))
    cost_idx = _find_col_priority(headers, ["成本价", "采购价", "商品成本价", "成本"], exclude=("售价", "吊牌"))
    if sp_idx < 0:
        sp_idx = cols.get("product_code", -1)
    if cost_idx < 0:
        cost_idx = cols.get("cost_price", -1)

    cost_map: dict[str, Decimal] = {}
    for row in rows_iter[header_row_idx + 1:]:
        price = _to_decimal(_cell(row, cost_idx))
        sp = _clean_no(_cell(row, sp_idx)) if sp_idx >= 0 else ""
        ks = _clean_no(_cell(row, ks_idx)) if ks_idx >= 0 else ""
        if sp:
            cost_map[sp] = price          # 商品编码（主键）
        if ks and ks not in cost_map:
            cost_map[ks] = price          # 款式编码（补充键，不覆盖商品编码）
    return cost_map


# ─── 注册 ─────────────────────────────────────────────────
PARSER_REGISTRY = {
    "order":             parse_order_file,
    "settlement":        parse_settlement_file,
    "after_sale":        parse_after_sale_file,
    "fund":              parse_fund_file,
    "freight":           parse_freight_file,
    "freight_insurance": parse_freight_insurance_file,
    "ad_cost":           parse_ad_cost_file,
    "product_cost":      parse_product_cost_file,
    "shipping_order":    parse_shipping_order_file,
}


def parse_one_for_generate(file_type: str, file_path, filename: str | None,
                           month: str, store_name: str) -> dict:
    """
    生成阶段单文件解析的“同步整包”入口：加载 + 解析。
    设计为可被 asyncio.to_thread 调用，把 CPU 阻塞从事件循环移走，
    从而避免几十万行解析时阻塞任务状态轮询接口。
    返回统一字典；解析失败抛异常由上层捕获。
    """
    wb = load_table_workbook(file_path, filename)
    try:
        if file_type == "order":
            diag: dict = {}
            orders = parse_order_file(wb, month, store_name, diag=diag)
            return {"orders": orders, "diag": diag}
        if file_type == "settlement":
            settlement_diag: dict = {}
            label_amount_map: dict[tuple[str, str], Decimal] = {}
            return {"settlement_map": parse_settlement_file(
                        wb, month, settlement_diag, label_amount_map),
                    "settlement_label_amount_map": label_amount_map,
                    "diag": settlement_diag}
        if file_type == "product_cost":
            return {"cost_map": parse_product_cost_file(wb)}
        if file_type == "shipping_order":
            ship_diag: dict = {}
            return {"shipping_by_product": parse_shipping_order_file(wb, month, diag=ship_diag), "diag": ship_diag}
        if file_type == "fund":
            fdiag: dict = {}
            return {"fund_agg": parse_fund_aggregates(wb, month, diag=fdiag), "diag": fdiag}
        if file_type == "freight":
            frdiag: dict = {}
            return {"freight": parse_freight_by_waybill(wb, diag=frdiag), "diag": frdiag}
        if file_type == "ad_cost":
            amt_diag: dict = {}
            amt = parse_amount_file(wb, file_type, diag=amt_diag)
            return {"amount": amt, "diag": amt_diag}
        return {}  # 其它（已停用类型）不参与计算
    finally:
        try:
            wb.close()
        except Exception:
            pass
