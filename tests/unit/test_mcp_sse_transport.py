"""Unit tests for SSE transport in MCP Server (H-3)."""

import json

import pytest

from src.llm_client.mcp.sse_transport import format_sse_event, stream_tool_result


class TestFormatSseEvent:
    """Test format_sse_event helper."""

    def test_format_sse_event_emits_correct_format(self):
        """Test format_sse_event emits correct SSE format."""
        # Run async function
        import asyncio

        result = asyncio.run(format_sse_event("tool_result", {"data": 1}))

        expected = 'event: tool_result\ndata: {"data": 1}\n\n'
        assert result == expected

    def test_format_sse_event_with_string_data(self):
        """Test format_sse_event with string data."""
        import asyncio

        result = asyncio.run(format_sse_event("done", "completed"))

        expected = "event: done\ndata: completed\n\n"
        assert result == expected

    def test_format_sse_event_with_list_data(self):
        """Test format_sse_event with list data."""
        import asyncio

        result = asyncio.run(format_sse_event("tool_result", [1, 2, 3]))

        expected = "event: tool_result\ndata: [1, 2, 3]\n\n"
        assert result == expected


class TestStreamToolResult:
    """Test stream_tool_result async generator."""

    @pytest.mark.asyncio
    async def test_stream_tool_result_emits_done_event(self):
        """Test stream_tool_result emits done event after chunks."""

        async def mock_handler():
            for i in range(3):
                yield {"chunk": f"result {i}"}

        events = []
        async for event in stream_tool_result(mock_handler()):
            events.append(event)

        # Should have 4 events: 3 tool_result + 1 done
        assert len(events) == 4

        # Parse events to verify content
        parsed_events = []
        for event in events:
            lines = event.strip().split("\n")
            assert lines[0].startswith("event: ")
            assert lines[1].startswith("data: ")
            parsed_events.append({"event": lines[0][7:], "data": json.loads(lines[1][6:])})

        # Check tool_result events
        assert parsed_events[0]["event"] == "tool_result"
        assert parsed_events[0]["data"] == {"chunk": "result 0"}
        assert parsed_events[1]["event"] == "tool_result"
        assert parsed_events[1]["data"] == {"chunk": "result 1"}
        assert parsed_events[2]["event"] == "tool_result"
        assert parsed_events[2]["data"] == {"chunk": "result 2"}

        # Check done event
        assert parsed_events[3]["event"] == "done"
        assert parsed_events[3]["data"] == {}

    @pytest.mark.asyncio
    async def test_stream_tool_result_emits_error_on_exception(self):
        """Test stream_tool_result emits error event on handler exception."""

        async def failing_handler():
            yield {"chunk": "first"}
            raise ValueError("Test error")

        events = []
        async for event in stream_tool_result(failing_handler()):
            events.append(event)

        # Should have 3 events: 1 tool_result + 1 error + 1 done
        assert len(events) == 3

        # Parse error event
        error_event = events[1]
        lines = error_event.strip().split("\n")
        assert lines[0] == "event: error"
        assert lines[1].startswith("data: ")
        error_data = json.loads(lines[1][6:])
        assert error_data["message"] == "Test error"

    @pytest.mark.asyncio
    async def test_stream_tool_result_with_single_result(self):
        """Test stream_tool_result with non-async-gen handler (single result)."""

        async def single_result_handler():
            return {"single": "result"}

        events = []
        async for event in stream_tool_result(single_result_handler):
            events.append(event)

        # Should have 2 events: 1 tool_result + 1 done
        assert len(events) == 2

        # Parse events
        parsed_events = []
        for event in events:
            lines = event.strip().split("\n")
            parsed_events.append({"event": lines[0][7:], "data": json.loads(lines[1][6:])})

        # Check tool_result event
        assert parsed_events[0]["event"] == "tool_result"
        assert parsed_events[0]["data"] == {"single": "result"}

        # Check done event
        assert parsed_events[1]["event"] == "done"
        assert parsed_events[1]["data"] == {}

    @pytest.mark.asyncio
    async def test_stream_tool_result_empty_handler(self):
        """Test stream_tool_result with empty handler."""

        async def empty_handler():
            # No chunks yielded
            return

        events = []
        async for event in stream_tool_result(empty_handler):
            events.append(event)

        # Should have 2 events: 1 tool_result (null) + 1 done
        assert len(events) == 2

        # Parse events
        parsed_events = []
        for event in events:
            lines = event.strip().split("\n")
            parsed_events.append({"event": lines[0][7:], "data": json.loads(lines[1][6:])})

        # Check tool_result event (null result from empty return)
        assert parsed_events[0]["event"] == "tool_result"
        assert parsed_events[0]["data"] is None

        # Check done event
        assert parsed_events[1]["event"] == "done"
        assert parsed_events[1]["data"] == {}
