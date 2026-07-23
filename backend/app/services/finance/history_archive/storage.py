"""本机与 MinIO 文件存储适配器。业务层不感知具体存储实现。"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


LOCAL_ROOT = Path(
    os.getenv(
        "HISTORY_ARCHIVE_LOCAL_ROOT",
        "/srv/mumaren_ai_platform/data/uploads/finance/history_archive",
    )
)


@dataclass
class PreparedDownload:
    path: Path
    temporary: bool = False


class ArchiveStorage:
    provider = "LOCAL"

    async def save(self, source: Path, key: str) -> None:
        raise NotImplementedError

    async def prepare_download(self, key: str) -> PreparedDownload:
        raise NotImplementedError

    async def discard_uncommitted(self, key: str) -> None:
        """只清理数据库尚未提交的失败上传，不处理已归档文件。"""


class LocalArchiveStorage(ArchiveStorage):
    provider = "LOCAL"

    def __init__(self, root: Path = LOCAL_ROOT):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        candidate.relative_to(self.root)
        return candidate

    async def save(self, source: Path, key: str) -> None:
        target = self._path(key)

        def _copy() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.uploading")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)

        await asyncio.to_thread(_copy)

    async def prepare_download(self, key: str) -> PreparedDownload:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return PreparedDownload(path=path)

    async def discard_uncommitted(self, key: str) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass


class MinioArchiveStorage(ArchiveStorage):
    provider = "MINIO"

    def __init__(self):
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - 仅 MinIO 部署触发
            raise RuntimeError("未安装 MinIO 客户端") from exc

        endpoint = os.getenv("HISTORY_ARCHIVE_MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("HISTORY_ARCHIVE_MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("HISTORY_ARCHIVE_MINIO_SECRET_KEY", "").strip()
        if not endpoint or not access_key or not secret_key:
            raise RuntimeError("MinIO 配置不完整")
        self.bucket = os.getenv("HISTORY_ARCHIVE_MINIO_BUCKET", "history-data-archive")
        secure = os.getenv("HISTORY_ARCHIVE_MINIO_SECURE", "true").lower() == "true"
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    async def _ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(self.client.bucket_exists, self.bucket)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, self.bucket)

    async def save(self, source: Path, key: str) -> None:
        await self._ensure_bucket()
        await asyncio.to_thread(self.client.fput_object, self.bucket, key, str(source))

    async def prepare_download(self, key: str) -> PreparedDownload:
        suffix = Path(key).suffix
        handle, name = tempfile.mkstemp(prefix="history_archive_", suffix=suffix)
        os.close(handle)
        path = Path(name)
        try:
            await asyncio.to_thread(self.client.fget_object, self.bucket, key, str(path))
        except Exception:
            path.unlink(missing_ok=True)
            raise FileNotFoundError(key)
        return PreparedDownload(path=path, temporary=True)

    async def discard_uncommitted(self, key: str) -> None:
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, key)
        except Exception:
            pass


def get_storage(provider: str | None = None) -> ArchiveStorage:
    selected = (provider or os.getenv("HISTORY_ARCHIVE_STORAGE_BACKEND", "LOCAL")).upper()
    if selected == "MINIO":
        return MinioArchiveStorage()
    if selected != "LOCAL":
        raise RuntimeError("不支持的历史存档存储类型")
    return LocalArchiveStorage()
