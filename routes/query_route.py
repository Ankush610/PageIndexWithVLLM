"""
routes/query_route.py — POST /query (agent-style RAG).
Named query_route to avoid shadowing the top-level query module.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import indexing
from models import QueryRequest, QueryResponse
from query import run_query_sync

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["query"])


@router.post("/query")
async def query_document(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        req  = QueryRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid request body: {exc}"
        ) from exc

    valid_ids = [
        d for d in req.resolved_doc_ids()
        if indexing.client and d in indexing.client.documents
    ]
    if not valid_ids:
        raise HTTPException(
            status_code=404,
            detail="None of the provided doc_ids are indexed.",
        )

    indexing.query_queue_depth += 1
    logger.info(
        "Query queue depth: %d (waiting for slot)", indexing.query_queue_depth
    )
    async with indexing.llm_semaphore:
        indexing.query_queue_depth -= 1
        logger.info(
            "LLM semaphore acquired for query (queue remaining: %d)",
            indexing.query_queue_depth,
        )
        try:
            result: QueryResponse = await asyncio.get_event_loop().run_in_executor(
                None, run_query_sync, req.query, valid_ids, indexing.client
            )
        except Exception as exc:
            exc_type = type(exc).__name__
            logger.error("Query failed [%s]: %s", exc_type, exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Query error [{exc_type}]: {exc}",
            ) from exc

    return JSONResponse(content=result.model_dump())
