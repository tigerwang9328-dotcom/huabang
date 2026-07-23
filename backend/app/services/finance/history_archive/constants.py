"""历史数据资产中心常量。"""
import os


ROOT_CATEGORIES = (
    "财务数据",
    "销售数据",
    "生产数据",
    "库存数据",
    "供应链数据",
    "人力数据",
    "税务数据",
    "其他数据",
)

DATA_TYPES = {"RAW_DATA", "FINANCIAL_REPORT", "ANALYSIS_REPORT"}
FILE_STATUSES = {"NORMAL", "DELETED"}
CATEGORY_STATUSES = {"ACTIVE", "INACTIVE"}
OPERATIONS = {"UPLOAD", "DOWNLOAD", "UPDATE", "DELETE", "RESTORE"}

ALLOWED_EXTENSIONS = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
}

MAX_FILE_SIZE = int(os.getenv("HISTORY_ARCHIVE_MAX_FILE_MB", "50")) * 1024 * 1024

PERM_MENU = "finance:history-archive"
PERM_VIEW = "finance:history-archive:view"
PERM_UPLOAD = "finance:history-archive:upload"
PERM_DOWNLOAD = "finance:history-archive:download"
PERM_UPDATE = "finance:history-archive:update"
PERM_DELETE = "finance:history-archive:delete"
PERM_CATEGORY = "finance:history-archive:category"
