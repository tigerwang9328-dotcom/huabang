from app.services.finance_v2.history_domain import (
    HistoryBatchError,
    HistoryBatchState,
    classify_source_record,
    transition_history_batch,
)


def test_history_batch_can_only_publish_after_validation():
    state = HistoryBatchState("created")
    state = transition_history_batch(state, "start_loading")
    state = transition_history_batch(state, "mark_loaded")
    state = transition_history_batch(state, "start_validation")
    state = transition_history_batch(state, "mark_validated")
    state = transition_history_batch(state, "publish")

    assert state.status == "published"


def test_history_batch_rejects_publish_from_loading():
    try:
        transition_history_batch(HistoryBatchState("loading"), "publish")
    except HistoryBatchError as error:
        assert "loading -> publish" in str(error)
    else:
        raise AssertionError("loading batch must not be published")


def test_same_source_key_is_idempotent_but_different_hash_is_conflict():
    assert classify_source_record("same", "same") == "already_imported"
    assert classify_source_record("same", "changed") == "conflict"
    assert classify_source_record(None, "changed") == "new"
