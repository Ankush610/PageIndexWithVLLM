from __future__ import annotations

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """One row in the GET /documents listing."""

    doc_id: str
    doc_name: str
    page_count: int = 0
    total_nodes: int = 0
    project: str = "default"


class DocumentsResponse(BaseModel):
    """Response body for GET /documents."""

    documents: list[DocumentSummary]


class DeleteResponse(BaseModel):
    """Response body for DELETE /document/{doc_id}."""

    status: str
    doc_id: str


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    model: str
    api_base: str
