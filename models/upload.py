from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UploadSettings(BaseModel):
    """Parsed from the 'settings' JSON string in POST /upload form data."""

    toc_check_page_num: int = Field(default=0, ge=0, le=30)
    max_page_num_each_node: int = Field(default=5, ge=2, le=30)
    max_token_num_each_node: int = Field(default=4000, ge=500, le=32000)
    if_add_node_summary: str = Field(default="no", pattern=r"^(yes|no)$")
    if_add_doc_description: str = Field(default="no", pattern=r"^(yes|no)$")
    use_llm_parser: bool = Field(default=False)
    project: str = Field(default="default")

    model_config = {"extra": "ignore"}  # silently drop unknown UI keys


class UploadFileResult(BaseModel):
    """Per-file outcome reported back to the UI after indexing."""

    doc_name: str
    success: bool
    doc_id: Optional[str] = None
    total_pages: Optional[int] = None
    total_nodes: Optional[int] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    """Response body for POST /upload."""

    results: list[UploadFileResult]
