"""Integration tests for message persistence with PII metadata."""

pytestmark = [pytest.mark.integration]
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from llm_client.agent.service import app
from llm_client.security.pii_detector import PIIDetector


@pytest.mark.asyncio
async def test_message_persistence_full_flow():
    """Test full message persistence flow: user message with PII + assistant response."""
    # Mock the pg_pool
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock ensure_chat_parents to return fixed UUIDs
    user_uuid = uuid.uuid4()
    session_uuid = uuid.uuid4()

    async def mock_ensure_parents(*args, **kwargs):
        return user_uuid, session_uuid

    # Mock insert_message to capture calls
    inserted_messages = []

    async def mock_insert_message(*args, **kwargs):
        inserted_messages.append(
            {
                "message_id": kwargs["message_id"],
                "session_id": kwargs["session_id"],
                "role": kwargs["role"],
                "content": kwargs["content"],
                "pii_score": kwargs["pii_score"],
                "pii_entities": kwargs["pii_entities"],
            }
        )

    # Mock other dependencies
    mock_redis = AsyncMock()
    mock_registry = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_pii_detector = AsyncMock(spec=PIIDetector)
    mock_pii_detector.enabled = True

    # Mock the graph and related components
    mock_graph = AsyncMock()
    mock_graph.astream.return_value = [
        # Assistant response chunk
        {"messages": [{"content": "Hello there!", "additional_kwargs": {}}]},
        # Final answer chunk
        {"final_answer": {"final_answer": "This is my response"}},
    ]

    mock_checkpointer = AsyncMock()
    mock_checkpointer_bundle = MagicMock()
    mock_checkpointer_bundle.checkpointer = mock_checkpointer
    mock_checkpointer_bundle.pg_pool = mock_pool

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.pii_metadata_enabled = True
    mock_settings.pii_detector_enabled = True
    mock_settings.pii_detector_spacy_model = "en_core_web_md"
    mock_settings.llm_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_invoke_timeout_seconds = 30
    mock_settings.rag_enabled = False

    # Mock LLM provider
    mock_llm = AsyncMock()
    mock_llm.return_value = "Mock response"

    # Patch dependencies in the app
    app.state.pg_pool = mock_pool
    app.state.redis = mock_redis
    app.state.registry = mock_registry
    app.state.subscriber = mock_subscriber
    app.state.pii_detector = mock_pii_detector
    app.state.checkpointer_bundle = mock_checkpointer_bundle

    # Patch the message_store functions
    with (
        patch("llm_client.agent.service.ensure_chat_parents", side_effect=mock_ensure_parents),
        patch("llm_client.agent.service.insert_message", side_effect=mock_insert_message),
        patch("llm_client.agent.service.LLMProviderFactory", return_value=mock_llm),
        patch("llm_client.agent.service.build_agent_graph", return_value=mock_graph),
        patch("llm_client.agent.service.resolve_tools", return_value=[]),
        patch("llm_client.agent.service.IterationMonitor", return_value=MagicMock()),
    ):
        # Test session creation and chat
        session_id = "test_session"
        user_id = "test_user"
        message = "My name is John and my email is john@test.com"

        # Create client and make request
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/sessions/{session_id}/chat",
                json={"message": message, "user_id": user_id},
            )

        # Verify response
        assert response.status_code == 202
        assert response.json() == {"status": "ok", "session_id": session_id}

        # Verify PII detection was called
        mock_pii_detector.detect.assert_called_once_with(message)

        # Verify user message was persisted
        assert len(inserted_messages) >= 1
        user_message = next(msg for msg in inserted_messages if msg["role"] == "user")

        assert user_message["session_id"] == session_uuid
        assert user_message["content"] == {"text": message}
        assert user_message["pii_score"] is not None
        assert user_message["pii_entities"] is not None
        assert len(user_message["pii_entities"]) > 0

        # Verify no PII text in entities
        for entity in user_message["pii_entities"]:
            assert "text" not in entity
            assert "type" in entity
            assert "start" in entity
            assert "end" in entity

        # Verify assistant message was persisted (if graph completed)
        assistant_messages = [msg for msg in inserted_messages if msg["role"] == "assistant"]
        if assistant_messages:
            assistant_msg = assistant_messages[0]
            assert assistant_msg["session_id"] == session_uuid
            assert assistant_msg["pii_score"] is None
            assert assistant_msg["pii_entities"] is None


@pytest.mark.asyncio
async def test_pii_metadata_disabled():
    """Test that PII columns are NULL when disabled."""
    # Mock the pg_pool
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock ensure_chat_parents to return fixed UUIDs
    user_uuid = uuid.uuid4()
    session_uuid = uuid.uuid4()

    async def mock_ensure_parents(*args, **kwargs):
        return user_uuid, session_uuid

    # Mock insert_message to capture calls
    inserted_messages = []

    async def mock_insert_message(*args, **kwargs):
        inserted_messages.append(
            {
                "pii_score": kwargs["pii_score"],
                "pii_entities": kwargs["pii_entities"],
            }
        )

    # Mock other dependencies
    mock_redis = AsyncMock()
    mock_registry = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_pii_detector = AsyncMock(spec=PIIDetector)
    mock_pii_detector.enabled = True

    # Mock the graph
    mock_graph = AsyncMock()
    mock_graph.astream.return_value = []

    mock_checkpointer = AsyncMock()
    mock_checkpointer_bundle = MagicMock()
    mock_checkpointer_bundle.checkpointer = mock_checkpointer
    mock_checkpointer_bundle.pg_pool = mock_pool

    # Mock settings with PII disabled
    mock_settings = MagicMock()
    mock_settings.pii_metadata_enabled = False  # PII disabled
    mock_settings.pii_detector_enabled = True
    mock_settings.pii_detector_spacy_model = "en_core_web_md"
    mock_settings.llm_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_invoke_timeout_seconds = 30
    mock_settings.rag_enabled = False

    # Mock LLM provider
    mock_llm = AsyncMock()
    mock_llm.return_value = "Mock response"

    # Patch dependencies
    app.state.pg_pool = mock_pool
    app.state.redis = mock_redis
    app.state.registry = mock_registry
    app.state.subscriber = mock_subscriber
    app.state.pii_detector = mock_pii_detector
    app.state.checkpointer_bundle = mock_checkpointer_bundle

    with (
        patch("llm_client.agent.service.ensure_chat_parents", side_effect=mock_ensure_parents),
        patch("llm_client.agent.service.insert_message", side_effect=mock_insert_message),
        patch("llm_client.agent.service.LLMProviderFactory", return_value=mock_llm),
        patch("llm_client.agent.service.build_agent_graph", return_value=mock_graph),
        patch("llm_client.agent.service.resolve_tools", return_value=[]),
        patch("llm_client.agent.service.IterationMonitor", return_value=MagicMock()),
    ):
        # Test session creation and chat
        session_id = "test_session"
        user_id = "test_user"
        message = "My name is John"

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/sessions/{session_id}/chat",
                json={"message": message, "user_id": user_id},
            )

        # Verify response
        assert response.status_code == 202

        # Verify user message was persisted with NULL PII columns
        assert len(inserted_messages) >= 1
        user_message = inserted_messages[0]

        assert user_message["pii_score"] is None
        assert user_message["pii_entities"] is None


@pytest.mark.asyncio
async def test_tool_message_persistence():
    """Test that tool messages are persisted."""
    # Mock the pg_pool
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock ensure_chat_parents to return fixed UUIDs
    user_uuid = uuid.uuid4()
    session_uuid = uuid.uuid4()

    async def mock_ensure_parents(*args, **kwargs):
        return user_uuid, session_uuid

    # Mock insert_message to capture calls
    inserted_messages = []

    async def mock_insert_message(*args, **kwargs):
        inserted_messages.append(
            {
                "role": kwargs["role"],
                "content": kwargs["content"],
            }
        )

    # Mock other dependencies
    mock_redis = AsyncMock()
    mock_registry = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_pii_detector = AsyncMock(spec=PIIDetector)
    mock_pii_detector.enabled = True

    # Mock graph with tool message
    mock_graph = AsyncMock()
    tool_message_content = {
        "tool_call_id": "call123",
        "tool_name": "search",
        "text": "Search results",
    }
    mock_graph.astream.return_value = [
        {"messages": [{"content": tool_message_content, "additional_kwargs": {}}]},
        {"final_answer": {"final_answer": "Based on search results..."}},
    ]

    mock_checkpointer = AsyncMock()
    mock_checkpointer_bundle = MagicMock()
    mock_checkpointer_bundle.checkpointer = mock_checkpointer
    mock_checkpointer_bundle.pg_pool = mock_pool

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.pii_metadata_enabled = True
    mock_settings.pii_detector_enabled = True
    mock_settings.pii_detector_spacy_model = "en_core_web_md"
    mock_settings.llm_provider = "openai"
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_invoke_timeout_seconds = 30
    mock_settings.rag_enabled = False

    # Mock LLM provider
    mock_llm = AsyncMock()
    mock_llm.return_value = "Mock response"

    # Patch dependencies
    app.state.pg_pool = mock_pool
    app.state.redis = mock_redis
    app.state.registry = mock_registry
    app.state.subscriber = mock_subscriber
    app.state.pii_detector = mock_pii_detector
    app.state.checkpointer_bundle = mock_checkpointer_bundle

    with (
        patch("llm_client.agent.service.ensure_chat_parents", side_effect=mock_ensure_parents),
        patch("llm_client.agent.service.insert_message", side_effect=mock_insert_message),
        patch("llm_client.agent.service.LLMProviderFactory", return_value=mock_llm),
        patch("llm_client.agent.service.build_agent_graph", return_value=mock_graph),
        patch("llm_client.agent.service.resolve_tools", return_value=[]),
        patch("llm_client.agent.service.IterationMonitor", return_value=MagicMock()),
    ):
        # Test session creation and chat
        session_id = "test_session"
        user_id = "test_user"
        message = "Search for something"

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/sessions/{session_id}/chat",
                json={"message": message, "user_id": user_id},
            )

        # Verify response
        assert response.status_code == 202

        # Verify tool message was persisted
        tool_messages = [msg for msg in inserted_messages if msg["role"] == "tool"]
        assert len(tool_messages) >= 1
        tool_msg = tool_messages[0]

        assert tool_msg["content"] == tool_message_content
        assert tool_msg["content"]["tool_call_id"] == "call123"
        assert tool_msg["content"]["tool_name"] == "search"
        assert tool_msg["content"]["text"] == "Search results"
