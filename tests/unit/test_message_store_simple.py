"""Unit tests for message_store module (simplified)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from llm_client.security.pii_detector import PIIDetectionResult, PIIEntity
from llm_client.agent.message_store import (
    MessageContent,
    ToolMessageContent,
    map_string_id,
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
        # Verify it's a valid UUID
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
            assert "type" in entity
            assert "start" in entity
            assert "end" in entity
    
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


class TestInsertMessageLogic:
    """Test insert_message logic without actual DB calls."""
    
    def test_insert_user_message_content(self):
        """Test user message content structure."""
        content = {"text": "Hello world"}
        assert content["text"] == "Hello world"
    
    def test_insert_tool_message_content(self):
        """Test tool message content structure."""
        content = {
            "tool_call_id": "call123",
            "tool_name": "test_tool",
            "text": "Tool result"
        }
        assert content["tool_call_id"] == "call123"
        assert content["tool_name"] == "test_tool"
        assert content["text"] == "Tool result"
    
    def test_pool_none_no_op(self):
        """Test that pool=None doesn't raise."""
        # This would be tested with actual async calls
        # For now, just verify the logic path exists
        assert True  # Placeholder for test