"""Tool calling adapter for ADR-016 Phase 3.

Central adapter that chooses between native/ReAct/hybrid tool calling modes based on
ModelCapabilityMatrix and ToolCallingMode enum.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import BaseTool

from llm_client.agent.capability_matrix import (
    ModelCapabilityMatrix,
    get_capability_matrix,
)
from llm_client.agent.tool_calling_mode import ToolCallingMode

logger = logging.getLogger(__name__)

# Regex to extract tool calls from ReAct responses (with or without ```json fences)
TOOL_CALL_REGEX = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\"tool\"[\s\S]*?\})\s*```|(\{[\s\S]*?\"tool\"[\s\S]*?\})",
    re.DOTALL,
)


def _to_openai_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Convert a parsed ReAct tool call to OpenAI function format.
    
    Args:
        tool_call: Parsed tool call from parse_react_response with 'tool'/'name' and 'arguments'/'args' keys
        
    Returns:
        Tool call in OpenAI format: {"id": "...", "function": {"name": "...", "arguments": "..."}}
    """
    name = tool_call.get("tool") or tool_call.get("name") or ""
    arguments = tool_call.get("arguments") or tool_call.get("args") or {}
    
    if isinstance(arguments, str):
        arguments_json = arguments
    else:
        arguments_json = json.dumps(arguments)
    
    return {
        "id": f"react_{uuid.uuid4().hex}",
        "function": {"name": name, "arguments": arguments_json},
    }


class ToolCallingAdapter:
    """Central adapter for tool calling mode selection and delegation."""

    def __init__(self, capability_matrix: ModelCapabilityMatrix | None = None):
        """Initialize with optional capability matrix (uses default if None)."""
        self._matrix = capability_matrix or get_capability_matrix()

    def choose_mode(
        self,
        provider: str,
        model: str,
        explicit_mode: ToolCallingMode | None = None,
    ) -> ToolCallingMode:
        """Choose tool calling mode for given provider/model.
        
        Args:
            provider: LLM provider name (e.g., "openai", "ollama")
            model: Model name (e.g., "gpt-4o-mini", "llama3.1-8b")
            explicit_mode: Override mode if provided
            
        Returns:
            Tool calling mode to use
        """
        if explicit_mode is not None:
            logger.info(
                "Using explicit tool calling mode: %s for %s/%s",
                explicit_mode,
                provider,
                model,
            )
            return explicit_mode

        caps = self._matrix.get_capabilities(provider, model)
        if caps is None:
            logger.warning(
                "No capability matrix entry for %s/%s, defaulting to HYBRID mode",
                provider,
                model,
            )
            mode = ToolCallingMode.HYBRID
        else:
            mode = ToolCallingMode.default_for_capabilities(caps)
            logger.info(
                "Tool calling mode for %s/%s: %s (capabilities: %s)",
                provider,
                model,
                mode,
                caps,
            )

        return mode

    def bind_tools(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        mode: ToolCallingMode,
    ) -> Any:
        """Bind tools to LLM using the specified mode.
        
        Args:
            llm: Base language model
            tools: List of tools to bind
            mode: Tool calling mode to use
            
        Returns:
            Bound model (native, ReActBoundModel, or HybridBoundModel)
        """
        if mode == ToolCallingMode.NATIVE:
            return llm.bind_tools(tools)
        elif mode == ToolCallingMode.REACT:
            return ReActBoundModel(underlying=llm, tools=tools, adapter=self)
        elif mode == ToolCallingMode.HYBRID:
            try:
                native_bound = llm.bind_tools(tools)
                return HybridBoundModel(
                    native_bound=native_bound,
                    react_bound=ReActBoundModel(underlying=llm, tools=tools, adapter=self),
                    adapter=self,
)
            except Exception as e:
                logger.warning(
                    "Native bind_tools failed (%s), falling back to ReAct for %s/%s",
                    e,
                    getattr(llm, "_default_provider", "unknown"),
                    getattr(llm, "_default_model", "unknown"),
                )
                return ReActBoundModel(underlying=llm, tools=tools, adapter=self)
        else:
            raise ValueError(f"Unknown ToolCallingMode: {mode}")

    def build_react_system_prompt(self, tools: list[BaseTool]) -> str:
        """Build ReAct system prompt with tool descriptions and schemas.

        Delegates to ReactToolCallPromptBuilder (D-4) — prompt variants are
        selectable via env REACT_PROMPT_VARIANT (default v1_strict).
        """
        from llm_client.agent.react_prompt_builder import get_react_prompt_builder

        return get_react_prompt_builder().build_prompt(tools)

    def parse_react_response(self, response_text: str) -> dict[str, Any] | None:
        """Parse tool calls from ReAct response text.
        
        Args:
            response_text: Response text from LLM
            
        Returns:
            Parsed tool call dict with 'tool'/'name' and 'arguments'/'args' keys, or None
        """
        # Use a simpler approach: look for JSON patterns and validate them
        # First, try to find complete JSON objects with proper structure
        
        # Pattern to find JSON objects that contain "tool"
        # Look for { ... "tool" ... } with balanced braces
        json_pattern = r"\{(?:[^{}]|\{[^{}]*\})*\"tool\"(?:[^{}]|\{[^{}]*\})*\}"
        matches = re.findall(json_pattern, response_text, re.DOTALL)
        
        for json_str in matches:
            try:
                parsed = json.loads(json_str)
                if "tool" in parsed or "name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
        
        # If that fails, try a more general approach
        # Look for any JSON object and check if it contains "tool"
        general_pattern = r"\{[\s\S]*?\}"
        candidates = re.findall(general_pattern, response_text, re.DOTALL)
        
        for json_str in candidates:
            try:
                parsed = json.loads(json_str)
                if "tool" in parsed or "name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
        
        # Finally, try to find fenced JSON
        fenced_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        fenced_matches = re.findall(fenced_pattern, response_text, re.DOTALL)
        
        for json_str in fenced_matches:
            try:
                parsed = json.loads(json_str)
                if "tool" in parsed or "name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
                
        return None


class ReActBoundModel:
    """Model wrapper that uses ReAct-style tool calling."""

    def __init__(
        self,
        underlying: BaseChatModel,
        tools: list[BaseTool],
        adapter: ToolCallingAdapter,
    ):
        """Initialize with underlying model, tools, and adapter."""
        self._underlying = underlying
        self._tools = tools
        self._tools_by_name = {tool.name: tool for tool in tools}
        self._adapter = adapter

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AIMessage:
        """Asynchronously invoke with ReAct-style tool calling."""
        # Inject system prompt
        system_prompt = self._adapter.build_react_system_prompt(self._tools)
        messages = [SystemMessage(content=system_prompt)] + messages
        
        # Get response from underlying model
        response = await self._underlying.ainvoke(messages, **kwargs)
        
        # Parse for tool calls
        content = response.content if isinstance(response.content, str) else str(response.content)
        tool_call = self._adapter.parse_react_response(content)
        if tool_call:
            # Convert to OpenAI format and create new AIMessage
            openai_tool_call = _to_openai_tool_call(tool_call)
            
            # Merge with existing tool calls (if any)
            existing_tool_calls = list(response.additional_kwargs.get("tool_calls") or [])
            existing_tool_calls.append(openai_tool_call)
            
            return AIMessage(
                content=response.content,
                additional_kwargs={
                    **response.additional_kwargs,
                    "tool_calls": existing_tool_calls,
                },
                response_metadata=response.response_metadata,
                usage_metadata=response.usage_metadata,
            )
        
        # No tool call found, return original response
        return response

    async def astream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ):
        """Asynchronously stream with ReAct-style tool calling."""
        # Inject system prompt
        system_prompt = self._adapter.build_react_system_prompt(self._tools)
        messages = [SystemMessage(content=system_prompt)] + messages
        
        accumulated_text = ""
        async for chunk in self._underlying.astream(messages, **kwargs):
            # Accumulate text content (handle both str and list content)
            if hasattr(chunk, "content"):
                content = chunk.content
                if isinstance(content, str):
                    accumulated_text += content
                else:
                    # Handle list of content blocks
                    accumulated_text += "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
            else:
                accumulated_text += str(chunk)
            
            yield chunk
        
        # After streaming, check for tool calls in accumulated text
        tool_call = self._adapter.parse_react_response(accumulated_text)
        if tool_call:
            # Convert to OpenAI format
            openai_tool_call = _to_openai_tool_call(tool_call)
            
            # Create final AIMessage with tool call
            yield AIMessage(
                content=accumulated_text,
                additional_kwargs={"tool_calls": [openai_tool_call]},
            )

    def __getattr__(self, name: str) -> Any:
        """Proxy to underlying model."""
        return getattr(self._underlying, name)


class HybridBoundModel:
    """Model wrapper that tries native first, falls back to ReAct."""

    def __init__(
        self,
        native_bound: Any,
        react_bound: ReActBoundModel,
        adapter: ToolCallingAdapter,
    ):
        """Initialize with native and ReAct bound models."""
        self._native_bound = native_bound
        self._react_bound = react_bound
        self._adapter = adapter

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AIMessage:
        """Asynchronously invoke with native fallback to ReAct."""
        try:
            # Try native first
            response = await self._native_bound.ainvoke(messages, **kwargs)
            
            # Check if native produced tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                return response
            
            # Check if native response contains a ReAct-style tool call in text
            tool_call = self._adapter.parse_react_response(response.content)
            if tool_call:
                # Native produced a tool call in text but not via API, fall back to ReAct
                logger.warning(
                    "Native model produced ReAct-style tool call in text but not via API, "
                    "falling back to ReAct mode"
                )
                return await self._react_bound.ainvoke(messages, **kwargs)
            
            # No tool calls found, return native response
            return response
            
        except Exception as e:
            logger.warning(
                "Native invocation failed (%s), falling back to ReAct",
                e,
            )
            return await self._react_bound.ainvoke(messages, **kwargs)

    async def astream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ):
        """Asynchronously stream with native fallback to ReAct."""
        try:
            # Try native first
            accumulated_text = ""
            async for chunk in self._native_bound.astream(messages, **kwargs):
                # Accumulate text for fallback detection
                if hasattr(chunk, "content"):
                    content = chunk.content
                    if isinstance(content, str):
                        accumulated_text += content
                    else:
                        accumulated_text += "".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                else:
                    accumulated_text += str(chunk)
                
                yield chunk
            
            # After native stream, check for tool calls
            tool_call = self._adapter.parse_react_response(accumulated_text)
            if tool_call:
                # Native produced a tool call in text but not via API, fall back to ReAct
                logger.warning(
                    "Native model produced ReAct-style tool call in text but not via API, "
                    "falling back to ReAct mode (double streaming may occur)"
                )
                async for react_chunk in self._react_bound.astream(messages, **kwargs):
                    yield react_chunk
            
        except Exception as e:
            logger.warning(
                "Native streaming failed (%s), falling back to ReAct",
                e,
            )
            async for react_chunk in self._react_bound.astream(messages, **kwargs):
                yield react_chunk

    def __getattr__(self, name: str) -> Any:
        """Proxy to native bound model."""
        return getattr(self._native_bound, name)


# Global singleton instance
_adapter_instance: ToolCallingAdapter | None = None


def get_tool_calling_adapter() -> ToolCallingAdapter:
    """Get global tool calling adapter instance (singleton)."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ToolCallingAdapter()
    return _adapter_instance