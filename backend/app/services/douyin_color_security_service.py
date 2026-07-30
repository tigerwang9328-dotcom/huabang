"""Security boundaries for the Douyin color collector payload contract."""

from __future__ import annotations

import hashlib
import gzip
import io
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, AsyncIterable
from urllib.parse import urlsplit, urlunsplit


_SENSITIVE_KEY_FRAGMENTS = (
    "cookie",
    "token",
    "authorization",
    "mstoken",
    "a_bogus",
    "signature",
    "password",
    "captcha",
    "set-cookie",
)
_HTTP_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_SCRIPT_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
_INLINE_SECRET = re.compile(r"(?i)\b(?:token|cookie|authorization|mstoken|a_bogus|signature|password|captcha)\s*[=:]\s*[^\s&#]+")
_SAFE_CREATOR_PAGE_PATH = re.compile(r"^/creator-micro/[A-Za-z0-9_/-]*$")


class DouyinPayloadSecurityError(ValueError):
    """Payload rejection that intentionally contains no untrusted value."""


async def read_bounded_body(chunks: AsyncIterable[bytes], *, max_bytes: int) -> bytes:
    """Read a request stream without allowing its compressed form to exhaust memory."""

    body = bytearray()
    async for chunk in chunks:
        body.extend(chunk)
        if len(body) > max_bytes:
            raise DouyinPayloadSecurityError("compressed_payload_too_large")
    return bytes(body)


def validate_gzip_content_encoding(content_encoding: str | None) -> None:
    """Require the transport boundary promised by the collector contract."""

    if content_encoding is None or content_encoding.lower().strip() != "gzip":
        raise DouyinPayloadSecurityError("gzip_required")


def hash_upload_token(token: str) -> str:
    """Derive the sole database lookup value for a collector upload token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_schema_version(*, schema_version: int, supported_versions: set[int]) -> None:
    """Fail closed instead of silently accepting a collector payload schema drift."""

    if schema_version not in supported_versions:
        raise DouyinPayloadSecurityError("schema_version_unsupported")


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _SCRIPT_VERSION.fullmatch(value)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())


def validate_collector_metadata(
    *, script_version: str, minimum_script_version: str, current_page_path: str | None
) -> None:
    """Reject unsupported collectors and page metadata that could contain secrets."""

    current = _version_tuple(script_version)
    minimum = _version_tuple(minimum_script_version)
    if current is None or minimum is None or current < minimum:
        raise DouyinPayloadSecurityError("script_version_too_old")
    if current_page_path is None:
        return
    if (
        _SAFE_CREATOR_PAGE_PATH.fullmatch(current_page_path) is None
    ):
        raise DouyinPayloadSecurityError("unsafe_page_path")


def decode_gzip_json(body: bytes, *, max_uncompressed_bytes: int) -> dict[str, Any]:
    """Decode one bounded gzip JSON object without accepting a decompression bomb."""

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as archive:
            raw = archive.read(max_uncompressed_bytes + 1)
    except (OSError, EOFError):
        raise DouyinPayloadSecurityError("invalid_gzip_body") from None
    if len(raw) > max_uncompressed_bytes:
        raise DouyinPayloadSecurityError("payload_too_large")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DouyinPayloadSecurityError("invalid_json_body") from None
    if not isinstance(decoded, dict):
        raise DouyinPayloadSecurityError("invalid_json_body")
    return decoded


def creator_fingerprint(creator_id: str) -> str:
    """Return the stored, one-way value for a transient creator identifier."""

    return hashlib.sha256(f"douyin-color-v31-creator-fingerprint:{creator_id}".encode("utf-8")).hexdigest()


def validate_observed_creator(*, expected_fingerprint: str, observed_creator_id: str) -> None:
    """Bind every upload to the creator identity configured for its token account."""

    if creator_fingerprint(observed_creator_id) != expected_fingerprint:
        raise DouyinPayloadSecurityError("creator_account_mismatch")


def sanitize_douyin_text(value: str | None, *, limit: int = 500) -> str | None:
    """Drop controls and URL query/fragment material before storage or logging."""

    if value is None:
        return None
    compact = _CONTROL_CHARACTERS.sub(" ", str(value))

    def strip_url(match: re.Match[str]) -> str:
        parsed = urlsplit(match.group(0))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    safe = _HTTP_URL_PATTERN.sub(strip_url, compact)
    safe = _INLINE_SECRET.sub("[REDACTED]", safe)
    return _WHITESPACE.sub(" ", safe).strip()[:limit]


def _contains_query_or_fragment(value: str) -> bool:
    for candidate in _HTTP_URL_PATTERN.findall(value):
        parsed = urlsplit(candidate)
        if parsed.query or parsed.fragment:
            return True
    return False


def validate_payload_safety(value: Any, *, path: str = "$") -> None:
    """Recursively reject sensitive fields and URL query/fragment material.

    Error values expose only a fixed code and a structural path; no original
    payload text is reflected to logs or API clients.
    """

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).lower()
            child_path = f"{path}.{key}"
            if normalized_key == "account_id":
                raise DouyinPayloadSecurityError("client_account_id_forbidden")
            if any(fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS):
                raise DouyinPayloadSecurityError(f"sensitive_field_detected:{child_path}")
            validate_payload_safety(child, path=child_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            validate_payload_safety(child, path=f"{path}[{index}]")
        return
    if isinstance(value, (bytes, bytearray)):
        raise DouyinPayloadSecurityError(f"invalid_binary_value:{path}")
    if isinstance(value, str):
        if _contains_query_or_fragment(value):
            raise DouyinPayloadSecurityError(f"signed_url_detected:{path}")
        if _INLINE_SECRET.search(value):
            raise DouyinPayloadSecurityError(f"sensitive_value_detected:{path}")
