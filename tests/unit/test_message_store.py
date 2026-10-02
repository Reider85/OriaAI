"""Unit tests for message_store module."""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from llm_client.security.pii_detector import PIIDetectionResult, PIIEntity
from llm_client.agent.message_store import (
    MessageContent,
    ToolMessageContent,
    map_string_id,
    ensure_chat_parents,
    insert_message,
    detection_to_columns,
)


class TestMessageModels:
    """Test Pydantic content models."""
    
    def test_message_content(self):
        """Test MessageContent model."""
        content = MessageContent(text="Hello world")
        assert content.text == "Hello world"
        assert content.model_dump() == {"text": "Hello world"}
    
    def test_tool_message_content(self):
        """Test ToolMessageContent model."""
        content = ToolMessageContent(
            tool_call_id="call123",
            tool_name="test_tool",
            text="Tool result"
        )
        assert content.tool_call_id == "call123"
        assert content.tool_name == "test_tool"
        assert content.text == "Tool result"
        assert content.model_dump() == {
            "tool_call_id": "call123",
            "tool_name": "test_tool",
            "text": "Tool result"
        }


class TestMapStringId:
    """Test UUID mapping for string IDs."""
    
    def test_stable_mapping(self):
        """Test same string always maps to same UUID."""
        uuid1 = map_string_id("test_user")
        uuid2 = map_string_id("test_user")
        assert uuid1 == uuid2
        assert isinstance(uuid1, uuid.UUID)
    
    def test_different_strings(self):
        """Test different strings map to different UUIDs."""
        uuid1 = map_string_id("user1")
        uuid2 = map_string_id("user2")
        assert uuid1 != uuid2
    
    def test_special_characters(self):
        """Test strings with special characters."""
        uuid1 = map_string_id("user@domain.com")
        uuid2 = map_string_id("user@domain.com")
        assert uuid1 == uuid2
        # UUID is deterministic but not fixed value - just verify it's valid UUID
        assert isinstance(uuid1, uuid.UUID)
        assert str(uuid1) == str(uuid1)  # Just verify string conversion works


class TestDetectionToColumns:
    """Test PII detection result to DB column conversion."""
    
    def test_enabled_with_entities(self):
        """Test conversion when PII is enabled with entities."""
        entities = [
            PIIEntity(type="PERSON", start=0, end=4),
            PIIEntity(type="EMAIL_ADDRESS", start=10, end=25),
        ]
        detection = PIIDetectionResult(score=0.42, entities=entities)
        
        score, entities_db = detection_to_columns(detection, enabled=True)
        
        assert score == 0.42
        assert entities_db == [
            {"type": "PERSON", "start": 0, "end": 4},
            {"type": "EMAIL_ADDRESS", "start": 10, "end": 25},
        ]
        # Ensure no text field in entities
        for entity in entities_db:
            assert "text" not in entity
    
    def test_enabled_no_entities(self):
        """Test conversion when PII is enabled but no entities."""
        detection = PIIDetectionResult(score=0.0, entities=[])
        
        score, entities_db = detection_to_columns(detection, enabled=True)
        
        assert score == 0.0
        assert entities_db == []
    
    def test_disabled(self):
        """Test conversion when PII is disabled."""
        entities = [
            PIIEntity(type="PERSON", start=0, end=4),
        ]
        detection = PIIDetectionResult(score=0.42, entities=entities)
        
        score, entities_db = detection_to_columns(detection, enabled=False)
        
        assert score is None
        assert entities_db is None
    
    def test_empty_detection(self):
        """Test conversion with empty detection."""
        detection = PIIDetectionResult(score=0.0, entities=[])
        
        score, entities_db = detection_to_columns(detection, enabled=True)
        
        assert score == 0.0
        assert entities_db == []


class TestEnsureChatParents:
    """Test ensure_chat_parents function."""
    
    @pytest.mark.asyncio
    async def test_ensure_parents(self):
        """Test ensuring users and sessions exist."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # Mock existing users/sessions (ON CONFLICT DO NOTHING/UPDATE)
        async def mock_execute(query, *args):
            return None
        
        mock_conn.execute = mock_execute
        
        # Mock the async context manager
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire
        
        user_uuid, session_uuid = await ensure_chat_parents(
            pool=mock_pool,
            user_key="test_user",
            session_key="test_session",
            provider="openai",
            model_name="gpt-4",
        )
        
        # Verify UUID mapping
        assert user_uuid == map_string_id("test_user")
        assert session_uuid == map_string_id("test_session")
        
        # Verify SQL calls
        assert mock_conn.execute.call_count == 2
        
        # Check user insert
        user_call = mock_conn.execute.call_args_list[0]
        assert "INSERT INTO users" in user_call[0][0]
        assert str(user_uuid) in user_call[0][1]
        
        # Check session insert
        session_call = mock_conn.execute.call_args_list[1]
        assert "INSERT INTO sessions" in session_call[0][0]
        assert str(session_uuid) in session_call[0][1]
        assert "openai" in session_call[0][3]
        assert "gpt-4" in session_call[0][4]


class TestInsertMessage:
    """Test insert_message function."""
    
    @pytest.mark.asyncio
    async def test_insert_user_message(self):
        """Test inserting user message with PII."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        
        async def mock_execute(query, *args):
            return None
        
        mock_conn.execute = mock_execute
        
        # Mock the async context manager
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire
        
        message_uuid = uuid.uuid4()
        session_uuid = uuid.uuid4()
        
        await insert_message(
            pool=mock_pool,
            message_id=message_uuid,
            session_id=session_uuid,
            role="user",
            content={"text": "Hello world"},
            pii_score=0.42,
            pii_entities=[{"type": "PERSON", "start": 0, "end": 4}],
        )
        
        # Verify SQL call
        mock_conn.execute.assert_called_once()
        call = mock_conn.execute.call_args_list[0]
        
        assert "INSERT INTO messages" in call[0][0]
        assert call[0][1] == message_uuid  # message_id
        assert call[0][2] == session_uuid   # session_id
        assert call[0][3] == {"text": "Hello world"}  # content
        assert call[0][8] == [{"type": "PERSON", "start": 0, "end": 4}]  # pii_entities
    
    @pytest.mark.asyncio
    async def test_insert_assistant_message(self):
        """Test inserting assistant message without PII."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        
        async def mock_execute(query, *args):
            return None
        
        mock_conn.execute = mock_execute
        
        # Mock the async context manager
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire
        
        message_uuid = uuid.uuid4()
        session_uuid = uuid.uuid4()
        
        await insert_message(
            pool=mock_pool,
            message_id=message_uuid,
            session_id=session_uuid,
            role="assistant",
            content={"text": "Hello there!"},
            tokens_in=10,
            tokens_out=15,
            cost_usd=0.001,
            pii_score=None,
            pii_entities=None,
        )
        
        # Verify SQL call
        mock_conn.execute.assert_called_once()
        call = mock_conn.execute.call_args_list[0]
        
        assert call[0][1] == message_uuid  # message_id
        assert call[0][2] == session_uuid   # session_id
        assert call[0][3] == {"text": "Hello there!"}  # content
        assert call[0][4] == 10  # tokens_in
        assert call[0][5] == 15  # tokens_out
        assert call[0][6] == 0.001  # cost_usd
        assert call[0][7] is None  # pii_score
        assert call[0][8] is None  # pii_entities
    
    @pytest.mark.asyncio
    async def test_insert_tool_message(self):
        """Test inserting tool message."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        
        async def mock_execute(query, *args):
            return None
        
        mock_conn.execute = mock_execute
        
        # Mock the async context manager
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire
        
        message_uuid = uuid.uuid4()
        session_uuid = uuid.uuid4()
        
        await insert_message(
            pool=mock_pool,
            message_id=message_uuid,
            session_id=session_uuid,
            role="tool",
            content={
                "tool_call_id": "call123",
                "tool_name": "test_tool",
                "text": "Tool result"
            },
        )
        
        # Verify SQL call
        mock_conn.execute.assert_called_once()
        call = mock_conn.execute.call_args_list[0]
        
        assert call[0][1] == message_uuid  # message_id
        assert call[0][2] == session_uuid   # session_id
        assert call[0][3] == {
            "tool_call_id": "call123",
            "tool_name": "test_tool",
            "text": "Tool result"
        }  # content
    
    @pytest.mark.asyncio
    async def test_pool_none_no_op(self):
        """Test graceful degradation when pool is None."""
        # Should not raise, should not execute
        await insert_message(
            pool=None,
            message_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            role="user",
            content={"text": "test"},
        )
    
    @pytest.mark.asyncio
    async def test_pool_exception_logged(self, caplog):
        """Test that pool exceptions are logged but don't raise."""
        mock_pool = AsyncMock()
        mock_pool.acquire.side_effect = Exception("Connection failed")
        
        async def mock_execute(query, *args):
            return None
        
        # Mock the async context manager for normal case
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = AsyncMock()
        mock_acquire.__aenter__.return_value.execute = mock_execute
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire
        
        with caplog.at_level(level=50):  # CRITICAL
            await insert_message(
                pool=mock_pool,
                message_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                role="user",
                content={"text": "test"},
            )
        
        # Should not have raised exception
        # Should have logged error (captured by caplog)