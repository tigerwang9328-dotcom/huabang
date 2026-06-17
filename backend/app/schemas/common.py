from pydantic import BaseModel
from typing import Any, Optional, Generic, TypeVar, List
from datetime import datetime

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: Optional[T] = None
    success: bool = True

    @classmethod
    def ok(cls, data: T = None, message: str = "success") -> "ApiResponse[T]":
        return cls(code=200, message=message, data=data, success=True)

    @classmethod
    def fail(cls, message: str, code: int = 400, data: Any = None) -> "ApiResponse":
        return cls(code=code, message=message, data=data, success=False)


class PageResult(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


class PageQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    keyword: Optional[str] = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class DateRangeQuery(PageQuery):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def safe_div(numerator: Any, denominator: Any, default: Any = None, pct: bool = False) -> Any:
    """安全除法，除数为0或None时返回default。pct=True时乘以100取百分比"""
    try:
        if denominator is None or denominator == 0:
            return default
        if numerator is None:
            return default
        result = float(numerator) / float(denominator)
        return round(result * 100, 2) if pct else round(result, 4)
    except (TypeError, ZeroDivisionError):
        return default
