"""输入校验与安全文件名处理。"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .constants import ALLOWED_EXTENSIONS, DATA_TYPES


def clean_text(value: str | None, *, maximum: int, required: bool = False) -> str:
    result = (value or "").strip()
    if required and not result:
        raise ValueError("必填字段不能为空")
    if len(result) > maximum:
        raise ValueError(f"字段长度不能超过{maximum}个字符")
    return result


def safe_filename(filename: str) -> str:
    result = (filename or "未命名文件").replace("\\", "/").rsplit("/", 1)[-1]
    return result[:512] or "未命名文件"


def file_extension(filename: str) -> tuple[str, str]:
    extension = Path(safe_filename(filename)).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 Excel、CSV、PDF 文件")
    return extension, ALLOWED_EXTENSIONS[extension]


def validate_period(year: int, month: int, start: date | None, end: date | None) -> None:
    if year < 1900 or year > 2100:
        raise ValueError("数据年份必须在1900至2100之间")
    if month < 1 or month > 12:
        raise ValueError("数据月份必须在1至12之间")
    if start and end and start > end:
        raise ValueError("数据开始日期不能晚于结束日期")


def validate_data_type(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized not in DATA_TYPES:
        raise ValueError("不支持的数据类型")
    return normalized


def safe_path_segment(value: str | None, fallback: str) -> str:
    result = clean_text(value, maximum=255) or fallback
    result = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", result)
    return result.strip(" .")[:100] or fallback
