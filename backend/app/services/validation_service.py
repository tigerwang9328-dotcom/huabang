"""导入数据验收服务：对13种数据类型做11维校验"""
import io
import csv
import json
import logging
from datetime import date, datetime
from typing import Any, Optional
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 系统标准字段定义：必填/类型/业务规则
FIELD_SPECS = {
    "sales_detail": {
        "detail_no":    {"required": True,  "type": "str",    "desc": "明细编号"},
        "order_no":     {"required": True,  "type": "str",    "desc": "单号"},
        "order_date":   {"required": True,  "type": "date",   "desc": "日期"},
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "sku_code":     {"required": False, "type": "str",    "desc": "SKU编码"},
        "quantity":     {"required": True,  "type": "int",    "desc": "数量", "min": 1},
        "actual_price": {"required": True,  "type": "decimal","desc": "实收单价", "min": 0},
        "actual_amount":{"required": True,  "type": "decimal","desc": "实收金额", "min": 0},
        "tag_price":    {"required": False, "type": "decimal","desc": "吊牌单价", "min": 0},
        "tag_amount":   {"required": False, "type": "decimal","desc": "吊牌金额", "min": 0},
        "cost_price":   {"required": False, "type": "decimal","desc": "成本价",   "min": 0},
        "channel":      {"required": False, "type": "str",    "desc": "渠道"},
        "guide_id":     {"required": False, "type": "str",    "desc": "导购编号"},
    },
    "return_detail": {
        "detail_no":    {"required": True,  "type": "str",    "desc": "明细编号"},
        "return_no":    {"required": True,  "type": "str",    "desc": "退货单号"},
        "return_date":  {"required": True,  "type": "date",   "desc": "退货日期"},
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "quantity":     {"required": True,  "type": "int",    "desc": "退货数量", "min": 1},
        "actual_amount":{"required": True,  "type": "decimal","desc": "退货金额", "min": 0},
    },
    "inventory": {
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "sku_code":     {"required": True,  "type": "str",    "desc": "SKU编码"},
        "quantity":     {"required": True,  "type": "int",    "desc": "库存数量"},
        "snapshot_date":{"required": True,  "type": "date",   "desc": "快照日期"},
        "cost_price":   {"required": False, "type": "decimal","desc": "成本价", "min": 0},
        "cost_amount":  {"required": False, "type": "decimal","desc": "成本金额", "min": 0},
        "age_days":     {"required": False, "type": "int",    "desc": "库龄天数", "min": 0},
    },
    "store": {
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "store_name":   {"required": True,  "type": "str",    "desc": "门店名称"},
        "channel":      {"required": True,  "type": "str",    "desc": "渠道"},
    },
    "product": {
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "product_name": {"required": True,  "type": "str",    "desc": "商品名称"},
    },
    "sku": {
        "sku_code":     {"required": True,  "type": "str",    "desc": "SKU编码"},
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "color":        {"required": False, "type": "str",    "desc": "颜色"},
        "size":         {"required": False, "type": "str",    "desc": "尺码"},
    },
    "member": {
        "member_no":    {"required": True,  "type": "str",    "desc": "会员编号"},
        "register_date":{"required": False, "type": "date",   "desc": "注册日期"},
        "total_amount": {"required": False, "type": "decimal","desc": "累计消费金额", "min": 0},
    },
    "employee": {
        "employee_id":  {"required": True,  "type": "str",    "desc": "导购编号"},
        "employee_name":{"required": True,  "type": "str",    "desc": "导购姓名"},
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
    },
    "sales_order": {
        "order_no":     {"required": True,  "type": "str",    "desc": "单号"},
        "order_date":   {"required": True,  "type": "date",   "desc": "日期"},
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "actual_amount":{"required": True,  "type": "decimal","desc": "实收金额", "min": 0},
    },
    "return_order": {
        "return_no":    {"required": True,  "type": "str",    "desc": "退货单号"},
        "return_date":  {"required": True,  "type": "date",   "desc": "退货日期"},
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
    },
    "finance_expense": {
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "expense_date": {"required": True,  "type": "date",   "desc": "费用日期"},
        "expense_type": {"required": True,  "type": "str",    "desc": "费用类型"},
        "expense_amount":{"required": True, "type": "decimal","desc": "费用金额", "min": 0},
    },
    "finance_cash": {
        "store_code":   {"required": True,  "type": "str",    "desc": "门店编码"},
        "record_date":  {"required": True,  "type": "date",   "desc": "记录日期"},
        "balance":      {"required": True,  "type": "decimal","desc": "现金余额"},
        "cash_type":    {"required": False, "type": "str",    "desc": "现金类型"},
    },
    "transfer": {
        "transfer_no":  {"required": True,  "type": "str",    "desc": "调拨单号"},
        "from_store":   {"required": True,  "type": "str",    "desc": "调出门店"},
        "to_store":     {"required": True,  "type": "str",    "desc": "调入门店"},
        "product_code": {"required": True,  "type": "str",    "desc": "款号"},
        "quantity":     {"required": True,  "type": "int",    "desc": "调拨数量", "min": 1},
        "transfer_date":{"required": True,  "type": "date",   "desc": "调拨日期"},
    },
}

# 阻断老板日报的数据类型（这些数据缺失会block report）
REPORT_CRITICAL_TYPES = {"sales_detail", "return_detail", "inventory"}
# 缺失会触发利润不可信警告
COST_RELATED_TYPES = {"inventory"}


def _coerce_value(value, field_type: str):
    """尝试转换字段值，返回(ok, converted_value, error_msg)"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True, None, None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return True, None, None

    try:
        if field_type == "str":
            return True, str(value), None
        elif field_type == "int":
            return True, int(float(str(value))), None
        elif field_type == "decimal":
            return True, float(str(value).replace(",", "")), None
        elif field_type == "date":
            if isinstance(value, (date, datetime)):
                return True, value, None
            parsed = pd.to_datetime(str(value), errors="coerce")
            if pd.isna(parsed):
                return False, None, f"无法解析日期: {value}"
            return True, parsed.date(), None
    except Exception as e:
        return False, None, str(e)
    return True, value, None


class ImportValidationService:
    """对已读取的DataFrame做11维校验，不写入数据库"""

    def validate(
        self,
        df: pd.DataFrame,
        data_type: str,
        batch_no: str,
        field_mapping: Optional[dict] = None,
    ) -> dict:
        """
        field_mapping: {excel_col -> system_field}，为None时认为列名已是系统字段
        返回11维验收结果
        """
        specs = FIELD_SPECS.get(data_type, {})
        if not specs:
            return {"error": f"不支持的数据类型: {data_type}"}

        # 应用字段映射
        if field_mapping:
            df = df.rename(columns={k: v for k, v in field_mapping.items() if v})

        total = len(df)
        errors = []
        missing_required = 0
        type_errors = 0
        biz_errors = 0
        success_rows = 0
        duplicate_detail = []

        # 重复检测（基于唯一键字段）
        unique_key = self._get_unique_key(data_type)
        duplicates_in_file = set()
        if unique_key and unique_key in df.columns:
            dup_mask = df[unique_key].duplicated(keep="first")
            duplicates_in_file = set(df[dup_mask].index.tolist())

        row_results = []
        for idx, row in df.iterrows():
            row_errors = []
            is_duplicate = idx in duplicates_in_file

            for field, spec in specs.items():
                raw_val = row.get(field)
                is_null = raw_val is None or (isinstance(raw_val, float) and pd.isna(raw_val)) or str(raw_val).strip() == ""

                # 1. 必填检查
                if spec["required"] and is_null:
                    row_errors.append({"field": field, "error_type": "missing_required",
                                       "value": None, "desc": f"{spec['desc']}（必填）缺失"})
                    continue

                if is_null:
                    continue

                # 2. 类型校验
                ok, converted, err_msg = _coerce_value(raw_val, spec["type"])
                if not ok:
                    row_errors.append({"field": field, "error_type": "type_error",
                                       "value": str(raw_val)[:50], "desc": f"{spec['desc']}类型错误: {err_msg}"})
                    continue

                # 3. 业务规则校验
                if converted is not None and "min" in spec:
                    if spec["type"] in ("int", "decimal") and float(str(converted)) < spec["min"]:
                        row_errors.append({"field": field, "error_type": "biz_error",
                                           "value": str(raw_val)[:50],
                                           "desc": f"{spec['desc']}={converted}，小于最小值{spec['min']}"})

            # 统计各类错误
            for e in row_errors:
                if e["error_type"] == "missing_required":
                    missing_required += 1
                elif e["error_type"] == "type_error":
                    type_errors += 1
                elif e["error_type"] == "biz_error":
                    biz_errors += 1

            row_result = {
                "row_no": idx + 2,  # Excel行号（含表头）
                "is_duplicate": is_duplicate,
                "errors": row_errors,
                "has_error": len(row_errors) > 0 or is_duplicate,
            }
            row_results.append(row_result)
            if not row_errors and not is_duplicate:
                success_rows += 1

        duplicate_count = len(duplicates_in_file)
        error_rows = total - success_rows - duplicate_count

        # 质量分：100 - (错误比例*60 + 重复比例*20 + 缺失比例*20)
        error_rate = error_rows / max(total, 1)
        dup_rate = duplicate_count / max(total, 1)
        missing_rate = missing_required / max(total * len(specs), 1)
        quality_score = max(0, round(100 - error_rate * 60 - dup_rate * 20 - missing_rate * 20, 1))

        # 是否允许ETL：error_rows=0，missing_required=0
        allow_etl = (error_rows == 0 and missing_required == 0 and type_errors == 0)
        # 是否阻断老板日报
        block_report = (data_type in REPORT_CRITICAL_TYPES and not allow_etl)

        # 只保留前100条错误明细
        error_detail = [r for r in row_results if r["has_error"]][:100]

        return {
            "batch_no": batch_no,
            "data_type": data_type,
            "total_rows": total,
            "success_rows": success_rows,
            "duplicate_rows": duplicate_count,
            "error_rows": error_rows,
            "missing_required_count": missing_required,
            "type_error_count": type_errors,
            "biz_error_count": biz_errors,
            "data_quality_score": quality_score,
            "allow_etl": allow_etl,
            "block_report": block_report,
            "error_detail": error_detail,
            "validated_fields": list(specs.keys()),
            "mapped_fields": [f for f in specs.keys() if f in df.columns],
            "unmapped_required": [f for f, s in specs.items() if s["required"] and f not in df.columns],
        }

    def _get_unique_key(self, data_type: str) -> Optional[str]:
        unique_keys = {
            "sales_order": "order_no", "sales_detail": "detail_no",
            "return_order": "return_no", "return_detail": "detail_no",
            "member": "member_no", "employee": "employee_id",
            "store": "store_code", "product": "product_code", "sku": "sku_code",
        }
        return unique_keys.get(data_type)

    def generate_field_mapping_table(self, data_type: str) -> list[dict]:
        """生成《百盛字段映射验收表》"""
        specs = FIELD_SPECS.get(data_type, {})
        from app.services.baison_import import FIELD_MAPPING
        baison_map = FIELD_MAPPING.get(data_type, {})
        reverse_map = {v: k for k, v in baison_map.items()}

        rows = []
        for field, spec in specs.items():
            baison_col = reverse_map.get(field, "")
            rows.append({
                "data_type": data_type,
                "system_field": field,
                "baison_excel_field": baison_col,
                "required": spec["required"],
                "data_type_desc": spec["type"],
                "description": spec["desc"],
                "is_mapped": bool(baison_col),
                "example": self._get_example(field, spec["type"]),
                "notes": "必填" if spec["required"] else "可选",
            })
        return rows

    def _get_example(self, field: str, field_type: str) -> str:
        examples = {
            "store_code": "S001", "product_code": "A2024001", "sku_code": "A2024001-BLK-M",
            "order_no": "SO20260601001", "detail_no": "SOD20260601001-1",
            "order_date": "2026-06-01", "quantity": "2", "actual_price": "299.00",
            "actual_amount": "598.00", "tag_price": "399.00", "cost_price": "120.00",
            "member_no": "M00001", "employee_id": "G001", "channel": "offline",
        }
        if field in examples:
            return examples[field]
        return {"str": "示例文本", "int": "1", "decimal": "0.00", "date": "2026-01-01"}.get(field_type, "")

    def generate_error_csv(self, validation_result: dict) -> bytes:
        """生成错误明细CSV（可下载）"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["行号", "错误类型", "字段", "错误值", "错误描述", "是否重复"])
        for row in validation_result.get("error_detail", []):
            row_no = row["row_no"]
            is_dup = row["is_duplicate"]
            if is_dup:
                writer.writerow([row_no, "duplicate", "", "", "文件内重复行", "是"])
            for e in row.get("errors", []):
                writer.writerow([row_no, e["error_type"], e["field"], e.get("value", ""),
                                 e["desc"], "否"])
        return output.getvalue().encode("utf-8-sig")
