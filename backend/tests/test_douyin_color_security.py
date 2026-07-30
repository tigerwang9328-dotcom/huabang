import pytest
import gzip
import json
from datetime import datetime, timezone
from pydantic import ValidationError


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


def test_recursive_payload_scan_rejects_sensitive_keys_and_signed_urls():
    from app.services.douyin_color_security_service import DouyinPayloadSecurityError, validate_payload_safety

    validate_payload_safety({"records": [{"video_id": "7666046377541012755", "curve": [[0, 1.0]]}]})

    with pytest.raises(DouyinPayloadSecurityError, match="sensitive_field_detected"):
        validate_payload_safety({"records": [{"nested": {"msToken": "secret"}}]})
    with pytest.raises(DouyinPayloadSecurityError, match="signed_url_detected"):
        validate_payload_safety({"cover_path": "https://example.invalid/cover.jpg?signature=redacted"})
    with pytest.raises(DouyinPayloadSecurityError, match="client_account_id_forbidden"):
        validate_payload_safety({"records": [{"account_id": 2}]})
    with pytest.raises(DouyinPayloadSecurityError, match="sensitive_value_detected"):
        validate_payload_safety({"records": [{"response_data": {"note": "token=secret"}}]})


def test_sanitize_douyin_text_removes_query_fragment_controls_and_limits_length():
    from app.services.douyin_color_security_service import sanitize_douyin_text

    cleaned = sanitize_douyin_text("bad\x00 https://creator.douyin.com/a?token=x#part")

    assert cleaned == "bad https://creator.douyin.com/a"
    assert len(sanitize_douyin_text("x" * 600)) == 500
    assert "secret" not in sanitize_douyin_text("upload failed token=secret")


def test_creator_fingerprint_is_deterministic_without_retaining_platform_id():
    from app.services.douyin_color_security_service import creator_fingerprint

    assert creator_fingerprint("creator-123") == creator_fingerprint("creator-123")
    assert creator_fingerprint("creator-123") != "creator-123"
    assert creator_fingerprint("creator-123") == "6c994b2e297611a398f54dab9e9ff4460cc5cf9a6c96cefd882bb0743768c0c8"


def test_gzip_json_decoder_rejects_plaintext_and_uncompressed_limit_overflow():
    from app.services.douyin_color_security_service import DouyinPayloadSecurityError, decode_gzip_json

    body = gzip.compress(json.dumps({"records": []}).encode("utf-8"))
    assert decode_gzip_json(body, max_uncompressed_bytes=100) == {"records": []}
    with pytest.raises(DouyinPayloadSecurityError, match="invalid_gzip_body"):
        decode_gzip_json(b'{"records": []}', max_uncompressed_bytes=100)
    with pytest.raises(DouyinPayloadSecurityError, match="payload_too_large"):
        decode_gzip_json(gzip.compress(b"x" * 101), max_uncompressed_bytes=100)


def test_collector_metadata_rejects_query_fragment_and_script_version_below_contract():
    from app.services.douyin_color_security_service import (
        DouyinPayloadSecurityError,
        validate_collector_metadata,
    )

    validate_collector_metadata(
        script_version="3.1.0",
        minimum_script_version="3.1.0",
        current_page_path="/creator-micro/data-center/content",
    )
    with pytest.raises(DouyinPayloadSecurityError, match="script_version_too_old"):
        validate_collector_metadata(
            script_version="3.0.9",
            minimum_script_version="3.1.0",
            current_page_path="/creator-micro/data-center/content",
        )
    with pytest.raises(DouyinPayloadSecurityError, match="unsafe_page_path"):
        validate_collector_metadata(
            script_version="3.1.0",
            minimum_script_version="3.1.0",
            current_page_path="/creator-micro/data-center/content?token=not-allowed",
        )
    with pytest.raises(DouyinPayloadSecurityError, match="unsafe_page_path"):
        validate_collector_metadata(
            script_version="3.1.0",
            minimum_script_version="3.1.0",
            current_page_path="/creator-micro/token=not-allowed",
        )


def test_upload_token_is_hashed_before_database_lookup():
    from app.services.douyin_color_security_service import hash_upload_token

    assert hash_upload_token("dyup_live_secret") != "dyup_live_secret"
    assert hash_upload_token("dyup_live_secret") == hash_upload_token("dyup_live_secret")
    assert len(hash_upload_token("dyup_live_secret")) == 64


def test_observed_creator_must_match_the_account_fingerprint():
    from app.services.douyin_color_security_service import (
        DouyinPayloadSecurityError,
        creator_fingerprint,
        validate_observed_creator,
    )

    expected = creator_fingerprint("creator-a")
    validate_observed_creator(expected_fingerprint=expected, observed_creator_id="creator-a")
    with pytest.raises(DouyinPayloadSecurityError, match="creator_account_mismatch"):
        validate_observed_creator(expected_fingerprint=expected, observed_creator_id="creator-b")


def test_schema_version_must_be_an_explicitly_supported_contract():
    from app.services.douyin_color_security_service import DouyinPayloadSecurityError, validate_schema_version

    validate_schema_version(schema_version=1, supported_versions={1})
    with pytest.raises(DouyinPayloadSecurityError, match="schema_version_unsupported"):
        validate_schema_version(schema_version=2, supported_versions={1})


def test_upload_body_requires_gzip_content_encoding():
    from app.services.douyin_color_security_service import DouyinPayloadSecurityError, validate_gzip_content_encoding

    validate_gzip_content_encoding("gzip")
    with pytest.raises(DouyinPayloadSecurityError, match="gzip_required"):
        validate_gzip_content_encoding(None)


@pytest.mark.asyncio
async def test_compressed_body_reader_rejects_oversize_before_collecting_full_request():
    from app.services.douyin_color_security_service import DouyinPayloadSecurityError, read_bounded_body

    assert await read_bounded_body(_chunks(b"12", b"34"), max_bytes=4) == b"1234"
    with pytest.raises(DouyinPayloadSecurityError, match="compressed_payload_too_large"):
        await read_bounded_body(_chunks(b"12", b"345"), max_bytes=4)


def test_collector_health_wire_fields_allow_only_machine_identifiers():
    from app.schemas.douyin_color_analytics import CollectorEventRequest, CollectorHeartbeatRequest

    CollectorHeartbeatRequest(
        installation_id="chrome-profile-1", script_version="3.1.0", schema_version=1,
        queued_batch_count=0, queued_bytes=0, current_page_type="content",
    )
    CollectorEventRequest(
        installation_id="chrome-profile-1", event_type="upload_failed", occurred_at=datetime.now(timezone.utc),
        error_category="network_failed", endpoint_name="collection_batches",
    )
    with pytest.raises(ValidationError):
        CollectorHeartbeatRequest(
            installation_id="token=secret", script_version="3.1.0", schema_version=1,
            queued_batch_count=0, queued_bytes=0,
        )
    with pytest.raises(ValidationError):
        CollectorEventRequest(
            installation_id="chrome-profile-1", event_type="upload_failed",
            occurred_at=datetime.now(timezone.utc), error_category="token=secret",
        )
