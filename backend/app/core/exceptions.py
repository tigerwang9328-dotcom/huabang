from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, code: int, message: str, data: any = None):
        self.code = code
        self.message = message
        self.data = data


class PermissionDeniedException(AppException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=403, message=message)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=404, message=message)


class DataQualityException(AppException):
    def __init__(self, message: str = "数据质量异常，AI诊断已暂停"):
        super().__init__(code=422, message=message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": exc.data,
            "success": False,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error[msg]}")
    return JSONResponse(
        status_code=200,
        content={
            "code": 400,
            "message": "请求参数错误",
            "data": errors,
            "success": False,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail,
            "data": None,
            "success": False,
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"未捕获异常: {request.method} {request.url} - {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误，请联系管理员",
            "data": None,
            "success": False,
        },
    )
