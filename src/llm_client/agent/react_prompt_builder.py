"""Builder for ReAct system prompts (ADR-016 Phase 3).

Constructs prompts with tool descriptions for ReAct-style tool calling on models
without native function calling (Llama, Mistral via Ollama).

Architecture: ARCHITECT.md v1.3.0 §5.2.4 (Tool Layer).
TRIZ: principle #1 (separation — tool description vs invocation).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal, cast

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

PromptVariant = Literal["v1_strict", "v2_tolerant", "v3_cot"]

DEFAULT_PROMPT_VARIANT: PromptVariant = "v1_strict"

PROMPT_VARIANTS: dict[str, str] = {
    "v1_strict": """You are a helpful assistant with access to the following tools:

{tool_descriptions}

When you want to use a tool, output EXACTLY this JSON format on a single line:
{{"tool": "<tool_name>", "arguments": {{<args>}}}}

Do not wrap the JSON in markdown fences. Do not add commentary before or after the JSON.
After the tool executes, you will receive a ToolMessage with the result.

Available tools:
{tool_schemas}
""",
    "v2_tolerant": """You are a helpful assistant with access to the following tools:

{tool_descriptions}

When you want to use a tool, you can output the JSON in any of these formats:
- On a single line: {{"tool": "...", "arguments": {{...}}}}
- In a markdown JSON block:
```json
{{"tool": "...", "arguments": {{...}}}}
```
- With brief commentary before: "Let me search for that.\\n{{"tool": "..."}}"

Available tools:
{tool_schemas}
""",
    "v3_cot": """You are a helpful assistant with access to these tools:

{tool_descriptions}

To use a tool, think step by step:
1. Determine which tool (if any) is needed.
2. Construct the arguments based on the user's request.
3. Output the tool call as JSON: {{"tool": "...", "arguments": {{...}}}}

You may wrap the JSON in markdown fences or output it inline.

Available tools (with schemas):
{tool_schemas}
""",
}


class ReactToolCallPromptBuilder:
    """Builds ReAct system prompts with tool descriptions."""

    def __init__(self, variant: PromptVariant = DEFAULT_PROMPT_VARIANT) -> None:
        self._variant = variant

    def build_prompt(self, tools: list[BaseTool]) -> str:
        """Build the ReAct system prompt for the given tools."""
        template = PROMPT_VARIANTS[self._variant]
        return template.format(
            tool_descriptions=self._format_tool_descriptions(tools),
            tool_schemas=self._format_tool_schemas(tools),
        )

    def _format_tool_descriptions(self, tools: list[BaseTool]) -> str:
        lines = []
        for tool in tools:
            desc = tool.description or "(no description)"
            lines.append(f"- {tool.name}: {desc}")
        return "\n".join(lines)

    def _format_tool_schemas(self, tools: list[BaseTool]) -> str:
        schemas = []
        for tool in tools:
            args_schema = getattr(tool, "args_schema", None)
            if args_schema is not None:
                try:
                    schema = args_schema.model_json_schema()
                    schemas.append(f"- {tool.name}: {json.dumps(schema, indent=2)}")
                except Exception as e:  # noqa: BLE001 — prompt construction must survive any schema error
                    logger.warning(
                        "Failed to serialize schema for tool %s: %s",
                        tool.name,
                        e,
                    )
                    schemas.append(f"- {tool.name}: (schema serialization failed)")
            else:
                schemas.append(f"- {tool.name}: (no schema)")
        return "\n".join(schemas)

    def variant(self) -> PromptVariant:
        return self._variant


_builder: ReactToolCallPromptBuilder | None = None


def get_react_prompt_builder(
    variant: PromptVariant | str | None = None,
) -> ReactToolCallPromptBuilder:
    """Singleton factory.

    Variant resolution order: explicit argument, then env
    REACT_PROMPT_VARIANT (default v1_strict). Unknown values fall back to
    v1_strict with a warning.
    """
    global _builder
    resolved = (
        variant
        if variant is not None
        else os.getenv("REACT_PROMPT_VARIANT", DEFAULT_PROMPT_VARIANT)
    )
    if resolved not in PROMPT_VARIANTS:
        logger.warning(
            "Unknown REACT_PROMPT_VARIANT %r, falling back to %s",
            resolved,
            DEFAULT_PROMPT_VARIANT,
        )
        resolved = DEFAULT_PROMPT_VARIANT
    effective = cast(PromptVariant, resolved)
    if _builder is None or _builder.variant() != effective:
        _builder = ReactToolCallPromptBuilder(variant=effective)
    return _builder
