from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ToolCallArgs(BaseModel):
    """Arguments payload inside a tool_call from the LLM."""

    doc_id: Optional[str] = None
    pages: Optional[str] = None

    model_config = {"extra": "allow"}  # forward-compatible with future tool args


class ToolCall(BaseModel):
    """The tool_call field emitted by the LLM agent."""

    tool: str
    args: ToolCallArgs = Field(default_factory=ToolCallArgs)


class AgentResponse(BaseModel):
    """Shape of every JSON response from the LLM inside the agent loop.

    The LLM is instructed to always output this schema.
    Parsing is attempted via AgentResponse.parse_llm(raw_text).
    """

    tool_call: Optional[ToolCall] = None
    answer: Optional[str] = None

    @field_validator("answer", mode="before")
    @classmethod
    def reject_null_string(cls, v: Any) -> Optional[str]:
        """Treat the literal string 'null' (from misbehaving LLMs) as None."""
        if isinstance(v, str) and v.strip().lower() == "null":
            return None
        return v

    @classmethod
    def parse_llm(cls, raw_text: str) -> "AgentResponse":
        """Parse raw LLM output into an AgentResponse.

        Handles:
          - Accidental markdown fences (```json ... ```)
          - Unescaped characters in the answer string (regex fallback)
          - Completely unparseable output (returns empty AgentResponse)
        """
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            return cls.model_validate_json(clean)
        except Exception:
            pass

        # Regex fallback: extract answer field from malformed JSON
        m = re.search(r'"answer"\s*:\s*"(.*)', clean, re.DOTALL)
        if m:
            candidate = m.group(1)
            candidate = re.sub(r'"\s*\}?\s*$', '', candidate).strip()
            if candidate and candidate.lower() != "null":
                return cls(answer=candidate.replace('\\"', '"').replace('\\n', '\n'))

        # If it doesn't look like a JSON blob, treat it as a plain-text answer
        if not clean.startswith('{'):
            return cls(answer=raw_text)

        # Completely unparseable JSON — return empty so the loop can retry
        return cls()
