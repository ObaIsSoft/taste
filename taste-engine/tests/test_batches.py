import json
from types import SimpleNamespace

import pytest

from taste_engine import batches


class FakeBatches:
    """client.messages.batches: create, retrieve and results."""

    def __init__(self, results):
        self.results_by_batch = results
        self.status = {}
        self.created = []

    def create(self, requests):
        batch_id = f"batch-{len(self.created) + 1}"
        self.created.append(requests)
        self.status[batch_id] = "in_progress"
        return SimpleNamespace(id=batch_id)

    def retrieve(self, batch_id):
        return SimpleNamespace(processing_status=self.status[batch_id])

    def results(self, batch_id):
        return iter(self.results_by_batch.get(batch_id, []))


def _client(results=None):
    return SimpleNamespace(messages=SimpleNamespace(batches=FakeBatches(results or {})))


def _request(i, pad=100):
    return {"custom_id": str(i), "params": {"pad": "x" * pad}}


def test_chunks_respect_the_size_limit():
    chunks = batches.chunk_requests([_request(i) for i in range(10)], max_bytes=400)
    assert sum(len(c) for c in chunks) == 10
    assert all(len(json.dumps(c)) <= 400 + 150 for c in chunks)


def test_submit_records_open_batches(fast_settings):
    client = _client()
    fast_settings.claude.batch_max_bytes = 400
    ids = batches.submit(fast_settings, client, "job", [_request(i) for i in range(10)])
    assert len(ids) > 1
    assert batches.open_batches(fast_settings, "job") == ids
    assert batches.open_batches(fast_settings, "other") == []


def test_unfinished_batches_stay_open(fast_settings):
    client = _client({"batch-1": ["a", "b"]})
    [first, second] = [
        batches.submit(fast_settings, client, "job", [_request(i)])[0] for i in range(2)
    ]
    client.messages.batches.status[first] = "ended"

    assert list(batches.collect(fast_settings, client, "job", wait=False)) == [
        (first, "a"),
        (first, "b"),
    ]
    assert batches.open_batches(fast_settings, "job") == [second]


def test_a_crash_while_handling_results_keeps_the_batch_open(fast_settings):
    client = _client({"batch-1": ["a", "b"]})
    [batch_id] = batches.submit(fast_settings, client, "job", [_request(1)])
    client.messages.batches.status[batch_id] = "ended"

    with pytest.raises(RuntimeError):
        for _ in batches.collect(fast_settings, client, "job", wait=False):
            raise RuntimeError("handler failed")
    assert batches.open_batches(fast_settings, "job") == [batch_id]


def _result(stop_reason="end_turn", text="hello", kind="succeeded"):
    message = SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )
    return SimpleNamespace(result=SimpleNamespace(type=kind, message=message))


def test_text_of_outcomes():
    assert batches.text_of(_result()) == ("hello", None)
    assert batches.text_of(_result(stop_reason="max_tokens")) == (None, "max_tokens")
    assert batches.text_of(_result(kind="expired")) == (None, "expired")
