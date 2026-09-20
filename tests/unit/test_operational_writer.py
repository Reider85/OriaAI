import json

import pytest

from llm_client.observability.operational_writer import (
    ELKSink,
    LokiSink,
    OperationalStreamWriter,
    StdoutSink,
)
from llm_client.security.pii_detector import PIIDetector


class CapturingSink:
    """Sink that records events so tests can inspect them."""

    def __init__(self):
        self.records: list[str] = []

    async def write_batch(self, events: list[str]) -> None:
        self.records.extend(events)


@pytest.fixture(scope="module")
def detector():
    return PIIDetector(spacy_model="en_core_web_md", enabled=True)


@pytest.fixture
def writer(detector):
    return OperationalStreamWriter(detector, sink=CapturingSink(), max_batch_size=100)


async def flush_until(writer, predicate, timeout=2.0):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await writer.flush()
        if predicate():
            return
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_write_masks_pii(detector):
    sink = CapturingSink()
    w = OperationalStreamWriter(detector, sink=sink)
    await w.write({"user": "john@example.com", "msg": "My name is John Doe"})
    await w.flush()
    assert len(sink.records) == 1
    event = json.loads(sink.records[0])
    assert event["user"] == "[EMAIL]"
    assert "[PERSON]" in event["msg"]
    assert "john@example.com" not in json.dumps(sink.records)


@pytest.mark.asyncio
async def test_nested_dict_resursively_masked(detector):
    sink = CapturingSink()
    w = OperationalStreamWriter(detector, sink=sink)
    # list containing an email inside a dict; also a string with a full name pattern
    await w.write(
        {"meta": {"contact": ["john@example.com"]}, "plain": "My name is Jane Doe"}
    )
    await w.flush()
    event = json.loads(sink.records[0])
    assert event["meta"]["contact"][0] == "[EMAIL]"
    assert "john@example.com" not in json.dumps(sink.records)


@pytest.mark.asyncio
async def test_batch_size_triggers_immediate_flush(detector):
    sink = CapturingSink()
    w = OperationalStreamWriter(detector, sink=sink, max_batch_size=3)
    for i in range(3):
        await w.write({"i": i, "text": f"plain event number {i}"})
    assert len(sink.records) == 3


@pytest.mark.asyncio
async def test_flush_interval_flushes(detector):
    sink = CapturingSink()
    w = OperationalStreamWriter(detector, sink=sink, flush_interval_ms=50, max_batch_size=100)
    await w.start()
    try:
        await w.write({"k": "v"})
        await flush_until(w, lambda: len(sink.records) >= 1)
        assert len(sink.records) >= 1
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_close_flushes_and_stops(detector):
    sink = CapturingSink()
    w = OperationalStreamWriter(detector, sink=sink, max_batch_size=100)
    await w.start()
    await w.write({"k": "something plain"})
    await w.close()
    assert len(sink.records) == 1
    # Further writes after close are dropped (writer is closed).
    await w.write({"k": "should not appear"})
    await w.flush()
    assert len(sink.records) == 1


@pytest.mark.asyncio
async def test_disabled_detector_writes_through(disabled_writer_factory):
    w = disabled_writer_factory()
    await w.write({"user": "john@example.com"})
    await w.flush()
    event = json.loads(w._sink.records[0])
    assert event["user"] == "john@example.com"


@pytest.fixture
def disabled_writer_factory():
    def factory():
        det = PIIDetector(spacy_model="en_core_web_md", enabled=False)
        return OperationalStreamWriter(det, sink=CapturingSink())

    return factory


# ---------------------------------------------------------------------------
# D-2 DoD: LokiSink tests (HTTP mock)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=204):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_loki_sink_sends_push_payload(detector):
    """LokiSink posts to /loki/api/v1/push with correct envelope."""
    captured = {}

    class FakeClient:
        async def post(self, url, json=None, **kw):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse(204)

        async def aclose(self):
            pass

    sink = LokiSink("http://fake-loki:3100")
    sink._client = FakeClient()
    w = OperationalStreamWriter(detector, sink=sink)
    await w.write({"msg": "test event plain text"})
    await w.flush()
    assert captured["url"] == "http://fake-loki:3100/loki/api/v1/push"
    body = captured["payload"]
    assert "streams" in body
    assert len(body["streams"]) == 1
    stream = body["streams"][0]
    assert stream["stream"]["app"] == "llm-client"
    assert stream["stream"]["source"] == "operational"
    assert len(stream["values"]) == 1
    # The value is [nanosecond_timestamp, json_line]
    assert len(stream["values"][0]) == 2


@pytest.mark.asyncio
async def test_loki_sink_empty_batch_noop(detector):
    """LokiSink does not POST when batch is empty."""
    post_called = False

    class FakeClient:
        async def post(self, url, **kw):
            nonlocal post_called
            post_called = True
            return FakeResponse(204)

        async def aclose(self):
            pass

    sink = LokiSink("http://fake:3100")
    sink._client = FakeClient()
    await sink.write_batch([])
    assert not post_called


@pytest.mark.asyncio
async def test_loki_sink_masks_pii_before_sending(detector):
    """LokiSink receives PII-masked events from OperationalStreamWriter."""
    captured = {}

    class FakeClient:
        async def post(self, url, json=None, **kw):
            captured["payload"] = json
            return FakeResponse(204)

        async def aclose(self):
            pass

    sink = LokiSink("http://fake:3100")
    sink._client = FakeClient()
    w = OperationalStreamWriter(detector, sink=sink)
    await w.write({"user": "john@example.com"})
    await w.flush()
    json_line = captured["payload"]["streams"][0]["values"][0][1]
    event = json.loads(json_line)
    assert event["user"] == "[EMAIL]"
    assert "john@example.com" not in json.dumps(captured["payload"])


# ---------------------------------------------------------------------------
# D-2 DoD: ELKSink tests (HTTP mock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_elk_sink_sends_bulk_payload(detector):
    """ELKSink posts NDJSON to /_bulk with correct action metadata."""
    captured = {}

    class FakeClient:
        async def post(self, url, content=None, headers=None, **kw):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse(200)

        async def aclose(self):
            pass

    sink = ELKSink("http://fake-es:9200")
    sink._client = FakeClient()
    w = OperationalStreamWriter(detector, sink=sink)
    await w.write({"msg": "plain event"})
    await w.flush()
    assert captured["url"] == "http://fake-es:9200/_bulk"
    assert captured["headers"]["Content-Type"] == "application/x-ndjson"
    lines = captured["content"].strip().split("\n")
    # NDJSON: action line + document line per event
    assert len(lines) == 2
    action = json.loads(lines[0])
    assert action["index"]["index"] == "llm-client-operational"
    doc = json.loads(lines[1])
    assert doc["msg"] == "plain event"


@pytest.mark.asyncio
async def test_elk_sink_empty_batch_noop(detector):
    """ELKSink does not POST when batch is empty."""
    post_called = False

    class FakeClient:
        async def post(self, url, **kw):
            nonlocal post_called
            post_called = True
            return FakeResponse(200)

        async def aclose(self):
            pass

    sink = ELKSink("http://fake:9200")
    sink._client = FakeClient()
    await sink.write_batch([])
    assert not post_called


@pytest.mark.asyncio
async def test_elk_sink_masks_pii(detector):
    """ELKSink receives PII-masked events."""
    captured = {}

    class FakeClient:
        async def post(self, url, content=None, **kw):
            captured["content"] = content
            return FakeResponse(200)

        async def aclose(self):
            pass

    sink = ELKSink("http://fake:9200")
    sink._client = FakeClient()
    w = OperationalStreamWriter(detector, sink=sink)
    await w.write({"email": "john@example.com"})
    await w.flush()
    lines = captured["content"].strip().split("\n")
    doc = json.loads(lines[1])
    assert doc["email"] == "[EMAIL]"
    assert "john@example.com" not in captured["content"]


# ---------------------------------------------------------------------------
# D-2 DoD: build_operational_writer factory
# ---------------------------------------------------------------------------

def test_build_operational_writer_stdout():
    from llm_client.observability.operational_writer import build_operational_writer

    class FakeSettings:
        operational_log_sink = "stdout"
        pii_detector_enabled = False
        pii_detector_spacy_model = "en_core_web_md"

    w = build_operational_writer(FakeSettings())
    assert isinstance(w._sink, StdoutSink)


def test_build_operational_writer_loki():
    from llm_client.observability.operational_writer import build_operational_writer

    class FakeSettings:
        operational_log_sink = "loki"
        operational_log_loki_url = "http://loki:3100"
        pii_detector_enabled = False
        pii_detector_spacy_model = "en_core_web_md"

    w = build_operational_writer(FakeSettings())
    assert isinstance(w._sink, LokiSink)


def test_build_operational_writer_elk():
    from llm_client.observability.operational_writer import build_operational_writer

    class FakeSettings:
        operational_log_sink = "elk"
        operational_log_es_url = "http://es:9200"
        pii_detector_enabled = False
        pii_detector_spacy_model = "en_core_web_md"

    w = build_operational_writer(FakeSettings())
    assert isinstance(w._sink, ELKSink)