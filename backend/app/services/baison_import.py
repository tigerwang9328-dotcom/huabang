"""百盛Excel数据导入服务（核心：去重/批次号/质量检查）"""
import uuid
import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Any
import pandas as pd
import io
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.models.log import LogDataSync
from app.models.ods import (
    OdsBaisonSalesOrder, OdsBaisonSalesDetail,
    OdsBaisonReturnOrder, OdsBaisonReturnDetail,
    OdsBaisonInventory, OdsBaisonMember, OdsBaisonEmployee,
    OdsBaisonStore, OdsBaisonProduct, OdsBaisonSku,
)

logger = logging.getLogger(__name__)

# 字段映射配置（百盛Excel列名 → 系统字段名）
FIELD_MAPPING = {
    "sales_order": {
        "单号": "order_no",
        "日期": "order_date",
        "门店编码": "store_code",
        "门店": "store_code",
        "渠道": "channel",
        "会员编号": "member_no",
        "导购编号": "guide_id",
        "吊牌金额": "tag_amount",
        "优惠金额": "discount_amount",
        "实收金额": "actual_amount",
        "销售件数": "item_count",
        "支付方式": "pay_type",
    },
    "sales_detail": {
        "明细编号": "detail_no",
        "单号": "order_no",
        "日期": "order_date",
        "门店编码": "store_code",
        "渠道": "channel",
        "款号": "product_code",
        "SKU编码": "sku_code",
        "颜色": "color",
        "尺码": "size",
        "数量": "quantity",
        "吊牌单价": "tag_price",
        "实收单价": "actual_price",
        "吊牌金额": "tag_amount",
        "实收金额": "actual_amount",
        "成本价": "cost_price",
        "折扣率": "discount_rate",
        "导购编号": "guide_id",
    },
    "inventory": {
        "快照日期": "snapshot_date",
        "门店编码": "store_code",
        "款号": "product_code",
        "SKU编码": "sku_code",
        "颜色": "color",
        "尺码": "size",
        "库存数量": "quantity",
        "成本价": "cost_price",
        "成本金额": "cost_amount",
        "库龄天数": "age_days",
    },
    "member": {
        "会员编号": "member_no",
        "姓名": "member_name",
        "手机": "phone",
        "性别": "gender",
        "生日": "birthday",
        "注册日期": "register_date",
        "注册门店": "register_store",
        "会员等级": "member_level",
        "累计消费金额": "total_amount",
        "累计消费次数": "total_count",
        "最后消费日期": "last_consume_date",
        "最后消费门店": "last_consume_store",
    },
    "store": {
        "门店编码": "store_code",
        "门店名称": "store_name",
        "区域": "region",
        "城市": "city",
        "渠道": "channel",
        "门店类型": "store_type",
        "面积": "area",
        "开业日期": "open_date",
        "状态": "status",
        "店长": "manager_name",
        "店长手机": "manager_phone",
        "地址": "address",
    },
}

MODEL_MAP = {
    "sales_order": OdsBaisonSalesOrder,
    "sales_detail": OdsBaisonSalesDetail,
    "return_order": OdsBaisonReturnOrder,
    "return_detail": OdsBaisonReturnDetail,
    "inventory": OdsBaisonInventory,
    "member": OdsBaisonMember,
    "employee": OdsBaisonEmployee,
    "store": OdsBaisonStore,
    "product": OdsBaisonProduct,
    "sku": OdsBaisonSku,
}

UNIQUE_KEY_MAP = {
    "sales_order": "order_no",
    "sales_detail": "detail_no",
    "return_order": "return_no",
    "return_detail": "detail_no",
    "inventory": None,  # 联合唯一键特殊处理
    "member": "member_no",
    "employee": "employee_id",
    "store": "store_code",
    "product": "product_code",
    "sku": "sku_code",
}


class BaisonImportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_excel(
        self,
        data_type: str,
        file_content: bytes,
        filename: str,
        operator_id: int,
    ) -> dict:
        batch_no = "BAISON_" + data_type.upper() + "_" + datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6].upper()
        start_at = datetime.now(timezone.utc)

        sync_log = LogDataSync(
            batch_no=batch_no,
            source_system="baison",
            data_type=data_type,
            sync_type="excel",
            file_name=filename,
            status="running",
            operator_id=operator_id,
        )
        self.db.add(sync_log)
        await self.db.flush()

        total = 0
        success = 0
        duplicate = 0
        errors = []

        try:
            df = self._read_excel(file_content, filename)
            df = self._apply_field_mapping(df, data_type)
            df = self._clean_dataframe(df)
            total = len(df)

            if total == 0:
                raise ValueError("Excel文件中无有效数据行")

            # 数据质量基础检查
            quality_issues = self._check_data_quality(df, data_type)
            if quality_issues:
                logger.warning(f"数据质量问题 [{batch_no}]: {quality_issues}")

            model_cls = MODEL_MAP.get(data_type)
            if not model_cls:
                raise ValueError(f"不支持的数据类型: {data_type}")

            for idx, row in df.iterrows():
                try:
                    row_dict = row.where(pd.notna(row), None).to_dict()
                    row_dict["batch_no"] = batch_no
                    row_dict["source"] = "excel"

                    # 去重检查
                    unique_key = UNIQUE_KEY_MAP.get(data_type)
                    if unique_key and unique_key in row_dict and row_dict[unique_key]:
                        exists = await self._check_exists(model_cls, unique_key, row_dict[unique_key])
                        if exists:
                            duplicate += 1
                            continue

                    obj = model_cls(**{k: v for k, v in row_dict.items() if hasattr(model_cls, k)})
                    self.db.add(obj)
                    success += 1

                    if success % 500 == 0:
                        await self.db.flush()

                except Exception as e:
                    errors.append({"row": int(idx) + 2, "error": str(e)[:200]})

            await self.db.flush()

            status = "success" if not errors else ("partial" if success > 0 else "failed")
            sync_log.status = status
            sync_log.total_rows = total
            sync_log.success_rows = success
            sync_log.duplicate_rows = duplicate
            sync_log.error_rows = len(errors)
            sync_log.error_detail = errors[:100]
            sync_log.end_at = datetime.now(timezone.utc)
            sync_log.duration_seconds = int((sync_log.end_at - start_at).total_seconds())

            return {
                "batch_no": batch_no,
                "total_rows": total,
                "success_rows": success,
                "duplicate_rows": duplicate,
                "error_rows": len(errors),
                "status": status,
                "errors": errors[:20],  # 前端只展示前20条
                "quality_issues": quality_issues,
            }

        except Exception as e:
            logger.exception(f"导入失败 [{batch_no}]: {e}")
            sync_log.status = "failed"
            sync_log.error_detail = [{"error": str(e)}]
            sync_log.end_at = datetime.now(timezone.utc)
            return {
                "batch_no": batch_no,
                "total_rows": total,
                "success_rows": 0,
                "duplicate_rows": 0,
                "error_rows": 0,
                "status": "failed",
                "errors": [{"error": str(e)}],
            }

    def _read_excel(self, content: bytes, filename: str) -> pd.DataFrame:
        buffer = io.BytesIO(content)
        if filename.lower().endswith(".csv"):
            return pd.read_csv(buffer, encoding="utf-8-sig", dtype=str)
        return pd.read_excel(buffer, dtype=str)

    def _apply_field_mapping(self, df: pd.DataFrame, data_type: str) -> pd.DataFrame:
        mapping = FIELD_MAPPING.get(data_type, {})
        rename_map = {col: mapping[col] for col in df.columns if col in mapping}
        return df.rename(columns=rename_map)

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna(how="all")
        df = df.reset_index(drop=True)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].str.strip() if hasattr(df[col], "str") else df[col]
        return df

    def _check_data_quality(self, df: pd.DataFrame, data_type: str) -> list[str]:
        issues = []
        if data_type == "sales_detail":
            if "actual_amount" in df.columns:
                neg = (pd.to_numeric(df["actual_amount"], errors="coerce") < 0).sum()
                if neg > 0:
                    issues.append(f"发现{neg}条实收金额为负的明细，请核查")
            if "cost_price" in df.columns:
                missing = pd.to_numeric(df["cost_price"], errors="coerce").isna().sum()
                if missing > 0:
                    issues.append(f"成本价缺失{missing}行，毛利计算将不完整")
        if data_type == "inventory":
            if "quantity" in df.columns:
                neg = (pd.to_numeric(df["quantity"], errors="coerce") < 0).sum()
                if neg > 0:
                    issues.append(f"发现{neg}条负库存记录")
        if data_type == "member":
            if "phone" in df.columns:
                empty = df["phone"].isna().sum()
                if empty > 0:
                    issues.append(f"手机号缺失{empty}条")
        return issues

    async def _check_exists(self, model_cls, unique_key: str, value: str) -> bool:
        result = await self.db.execute(
            select(model_cls.id).where(getattr(model_cls, unique_key) == value).limit(1)
        )
        return result.scalar_one_or_none() is not None
