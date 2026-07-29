from types import SimpleNamespace

import pytest

from app.services.finance_v2 import posting_attempt_service
from app.services.finance_v2.posting_attempt_service import FinanceV2PostingAttemptRecorder


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _AttemptSession:
    def __init__(self, attempts):
        self.attempts = attempts
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        command_id = getattr(_statement, "_where_criteria", ())
        existing = next((item for item in self.attempts if item.command_id == "post-command-1"), None)
        return _Result(existing)

    def add(self, item):
        item.id = len(self.attempts) + 1
        self.attempts.append(item)
        self.added.append(item)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def get(self, _model, attempt_id):
        return next((item for item in self.attempts if item.id == attempt_id), None)


class _SessionFactory:
    def __init__(self):
        self.attempts = []
        self.sessions = []

    def __call__(self):
        session = _AttemptSession(self.attempts)
        self.sessions.append(session)
        return session


def test_posting_attempt_recorder_defers_finance_session_configuration_until_an_attempt_starts(monkeypatch):
    def fail_if_requested():
        raise AssertionError("finance session should not be configured before a post attempt")

    monkeypatch.setattr(posting_attempt_service, "get_finance_session_factory", fail_if_requested)

    FinanceV2PostingAttemptRecorder()


@pytest.mark.asyncio
async def test_posting_attempt_lifecycle_uses_separate_committed_sessions_and_sanitizes_failure_context():
    factory = _SessionFactory()
    recorder = FinanceV2PostingAttemptRecorder(factory)

    attempt_id = await recorder.start(voucher_id=7, command_id="post-command-1")
    await recorder.mark_failed(
        attempt_id,
        error_code="ledger_rebuild_failed",
        error_context={"database_url": "postgres://secret", "detail": "ledger mismatch"},
    )

    assert len(factory.sessions) == 2
    assert [session.commits for session in factory.sessions] == [1, 1]
    attempt = factory.attempts[0]
    assert attempt.id == attempt_id
    assert attempt.status == "failed"
    assert attempt.error_code == "ledger_rebuild_failed"
    assert attempt.error_context["database_url"] == "[redacted]"
    assert attempt.error_context["detail"] == "ledger mismatch"


@pytest.mark.asyncio
async def test_posting_attempt_default_uses_the_restricted_finance_session_factory(monkeypatch):
    factory = _SessionFactory()
    monkeypatch.setattr(posting_attempt_service, "get_finance_session_factory", lambda: factory)

    recorder = FinanceV2PostingAttemptRecorder()
    attempt_id = await recorder.start(voucher_id=9, command_id="post-command-finance-session")

    assert attempt_id == 1
    assert len(factory.sessions) == 1
