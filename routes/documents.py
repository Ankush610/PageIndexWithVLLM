"""
routes/documents.py — Document listing and deletion endpoints.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import indexing
from config import WORKSPACE_DIR
from models import DeleteResponse, DocumentsResponse, DocumentSummary

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def list_documents() -> JSONResponse:
    """Return a summary of all indexed documents."""
    summaries = [
        DocumentSummary(
            doc_id=d.get("doc_id") or did,
            doc_name=d.get("doc_name", ""),
            page_count=d.get("page_count", 0),
            total_nodes=d.get("total_nodes", 0),
            project=d.get("project", "default"),
        )
        for did, d in (indexing.client.documents if indexing.client else {}).items()
    ]
    return JSONResponse(content=DocumentsResponse(documents=summaries).model_dump())


@router.delete("/document/{doc_id}")
async def delete_document(doc_id: str) -> JSONResponse:
    """Remove a document from the store and delete its workspace files."""
    if not indexing.client or doc_id not in indexing.client.documents:
        raise HTTPException(
            status_code=404, detail=f"Document '{doc_id}' not found."
        )

    indexing.client.documents.pop(doc_id)

    for suffix in (".pdf", ".json"):
        p = WORKSPACE_DIR / f"{doc_id}{suffix}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    if indexing.client.workspace:
        meta = indexing.client._read_meta() or {}
        meta.pop(doc_id, None)
        meta_path = indexing.client.workspace / "_meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    return JSONResponse(
        content=DeleteResponse(status="deleted", doc_id=doc_id).model_dump()
    )
