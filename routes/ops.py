"""
routes/ops.py — Operational / monitoring endpoints:
    GET  /health
    GET  /log_latest
    GET  /indexing_phase
    GET  /queue_status
    POST /cancel_indexing
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import indexing
from config import INDEXER_MODEL, OPENAI_API_BASE
from indexing import find_latest_log, read_log_safe
from models import HealthResponse

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", model=INDEXER_MODEL, api_base=OPENAI_API_BASE
    )


@router.get("/log_latest")
async def log_latest() -> JSONResponse:
    log_path = find_latest_log()
    if not log_path or not os.path.exists(log_path):
        return JSONResponse(content=[])
    return JSONResponse(content=read_log_safe(log_path))


@router.get("/indexing_phase")
async def get_indexing_phase() -> JSONResponse:
    """Returns the current phase of the active indexing job.
    phase values: 'idle' | 'pageindex' | 'page_extract' | 'done'
    """
    return JSONResponse(content={
        "phase": indexing.indexing_phase,
        "file":  indexing.indexing_phase_file,
    })


@router.get("/queue_status")
async def queue_status() -> JSONResponse:
    """Returns semaphore / queue state for the UI's status badge."""
    busy = (
        indexing.llm_semaphore.locked()
        if hasattr(indexing.llm_semaphore, "locked")
        else (indexing.llm_semaphore._value == 0)
    )
    return JSONResponse(content={
        "index_busy":    busy,
        "index_waiting": indexing.index_queue_depth,
        "query_busy":    busy,
        "query_waiting": indexing.query_queue_depth,
    })


@router.post("/cancel_indexing")
async def cancel_indexing() -> JSONResponse:
    """Request cancellation after the current document finishes indexing."""
    indexing.request_cancel()
    logger.info("Cancel requested — will stop after current document completes")
    return JSONResponse(content={"status": "cancel_requested"})
