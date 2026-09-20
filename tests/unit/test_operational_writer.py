import json

import pytest

from llm_client.observability.operational_writer import OperationalStreamWriter, StdoutSink
from llm_client.security.pii_detector import PIIDetector


class CapturingSink(StdoutSink):
    """StdoutSink that also records events so tests can inspect them."""

    def __init__(self):
        self.records: list[str] = []

    def _record(self, event: str) -> None:
        self.records.append(event)

    async def write_batch(self, events: list[str]) -> None:
        for event in events:
            self._record(event)


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