from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    query: str = Field(..., min_length=1)
    doc_id: Optional[str] = None
    doc_ids: Optional[list[str]] = None

    @model_validator(mode="after")
    def at_least_one_doc(self) -> "QueryRequest":
        if not self.doc_id and not self.doc_ids:
            raise ValueError("At least one of 'doc_id' or 'doc_ids' must be provided.")
        return self

    def resolved_doc_ids(self) -> list[str]:
        """Return the definitive list of doc IDs to query."""
        if self.doc_ids:
            return self.doc_ids
        return [self.doc_id]  # type: ignore[list-item]


class TraversalStep(BaseModel):
    """One tool invocation recorded during the agent loop."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_preview: str = ""


class ContextPassage(BaseModel):
    """One retrieved section shown in the UI context panel."""

    relevant: bool = True
    section_title: str = ""
    page_number: Optional[int] = None
    passages: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """Response body for POST /query."""

    answer: str
    traversal: list[TraversalStep] = Field(default_factory=list)
    context: list[ContextPassage] = Field(default_factory=list)
    doc_name: str = ""
