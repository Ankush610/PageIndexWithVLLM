"""
routes/upload.py — POST /upload
Accepts one or more PDF files, indexes them, returns per-file results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

import indexing
from config import (
    CONFIGLOADER_KEYS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    PAGEINDEX_OPTS_DEFAULT,
    WORKSPACE_DIR,
)
from models import UploadFileResult, UploadResponse, UploadSettings

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["indexing"])


@router.post("/upload")
async def upload(
    files: list[UploadFile] = File(..., description="PDF files to index"),
    settings: str = Form(default=""),
):
    """Index one or more documents.  Accepts multipart/form-data with:
      - files    : one or more files
      - settings : JSON string with indexing knobs from the UI settings panel
    """
    global _index_queue_depth  # noqa: PLW0603

    indexing.index_queue_depth += 1
    logger.info(
        "Index queue depth: %d (waiting for slot)", indexing.index_queue_depth
    )
    async with indexing.llm_semaphore:
        indexing.index_queue_depth -= 1
        logger.info(
            "LLM semaphore acquired for indexing (queue remaining: %d)",
            indexing.index_queue_depth,
        )
        result = await _upload_inner(files, settings)
    return result


async def _upload_inner(
    files: list[UploadFile],
    settings: str,
) -> JSONResponse:
    """Actual upload logic — runs only when the LLM semaphore is held."""

    ui_settings = UploadSettings()
    if settings:
        try:
            ui_settings = UploadSettings.model_validate_json(settings)
        except Exception:
            logger.warning(
                "Could not parse settings JSON: %r — using defaults", settings
            )

    use_llm_parser: bool = ui_settings.use_llm_parser
    logger.info("use_llm_parser=%s", use_llm_parser)
    logger.info("Full ui_settings received: %s", ui_settings.model_dump())
    logger.info(
        "Page extraction pipeline: %s",
        "LLM vision" if use_llm_parser else "PyMuPDF",
    )

    opts = {**PAGEINDEX_OPTS_DEFAULT}
    for key, val in ui_settings.model_dump().items():
        if key in CONFIGLOADER_KEYS:
            opts[key] = val
    logger.info(
        "Indexing opts from UI: %s",
        {k: opts[k] for k in CONFIGLOADER_KEYS if k in opts},
    )

    results: list[UploadFileResult] = []

    for file in files:
        if indexing.cancel_after_current:
            logger.info(
                "Cancel flag set — skipping '%s' and remaining files", file.filename
            )
            indexing.clear_cancel()
            break

        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext != ".pdf":
            results.append(UploadFileResult(
                doc_name=filename, success=False,
                error=f"Unsupported type '{ext}'. Only PDF accepted.",
            ))
            continue

        raw_bytes = await file.read()

        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            results.append(UploadFileResult(
                doc_name=filename, success=False,
                error=f"Exceeds {MAX_UPLOAD_MB} MB limit.",
            ))
            continue

        if not raw_bytes:
            results.append(UploadFileResult(
                doc_name=filename, success=False, error="Empty file."
            ))
            continue

        if ext == ".pdf" and not raw_bytes.startswith(b"%PDF-"):
            results.append(UploadFileResult(
                doc_name=filename, success=False,
                error="Not a valid PDF (missing %PDF- header).",
            ))
            continue

        tmp_path: str | None = None
        doc_id: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=f"_{uuid.uuid4().hex}{ext}", delete=False
            ) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name

            logger.info(
                "Saved '%s' (%d B) → %s", filename, len(raw_bytes), tmp_path
            )

            if ext == ".pdf":
                indexing.set_phase("pageindex", filename)

                # Detect scanned PDF before tree building so we can reuse
                # the vision pages for the retrieval layer too (avoids double extraction)
                is_scanned = await asyncio.get_event_loop().run_in_executor(
                    None, indexing._is_scanned_pdf, tmp_path
                )
                # Force vision parser for scanned PDFs regardless of UI toggle
                effective_use_vision = use_llm_parser or is_scanned
                if is_scanned and not use_llm_parser:
                    logger.info(
                        "Scanned PDF detected for '%s' — forcing LLM Vision pipeline", filename
                    )

                result_dict = await asyncio.get_event_loop().run_in_executor(
                    None, indexing.run_pageindex_sync, tmp_path, dict(opts)
                )
                indexing.find_latest_log()  # refresh log pointer
                indexing.set_phase("page_extract", filename)

                structure  = result_dict.get("structure", [])
                doc_name   = filename
                # If scanned, vision extraction already ran inside run_pageindex_sync.
                # Re-run it here for the pages array (retrieval layer).
                # For non-scanned PDFs respect the UI toggle as before.
                _extractor = (
                    indexing.extract_pages_llm_vision
                    if effective_use_vision
                    else indexing.extract_pages_pymupdf
                )
                pages_list = await asyncio.get_event_loop().run_in_executor(
                    None, _extractor, tmp_path
                )
                indexing.set_phase("done", filename)

                total_pages = len(pages_list)
                total_nodes = indexing.count_tree_nodes(structure)
                doc_id      = str(uuid.uuid4())

                pdf_dest = WORKSPACE_DIR / f"{doc_id}.pdf"
                shutil.copyfile(tmp_path, str(pdf_dest))

                indexing.client.documents[doc_id] = {
                    "doc_id":          doc_id,
                    "doc_name":        doc_name,
                    "type":            "pdf",
                    "path":            str(pdf_dest),
                    "structure":       structure,
                    "pages":           pages_list,
                    "page_count":      total_pages,
                    "total_nodes":     total_nodes,
                    "doc_description": result_dict.get("doc_description", ""),
                    "project":         ui_settings.project or "default",
                }
                indexing.client._save_doc(doc_id)

                results.append(UploadFileResult(
                    doc_name=doc_name,
                    doc_id=doc_id,
                    success=True,
                    total_pages=total_pages,
                    total_nodes=total_nodes,
                ))
                logger.info(
                    "Indexed '%s': %d pages, %d nodes",
                    doc_name, total_pages, total_nodes,
                )


        except Exception as exc:
            exc_type = type(exc).__name__
            logger.error(
                "Indexing '%s' failed [%s]: %s",
                filename, exc_type, exc, exc_info=True,
            )
            results.append(UploadFileResult(
                doc_name=filename, success=False, error=f"{exc_type}: {exc}",
            ))
            # Clean up any partial workspace files
            if doc_id:
                indexing.client.documents.pop(doc_id, None)
                for suffix in (".pdf", ".json"):
                    p = WORKSPACE_DIR / f"{doc_id}{suffix}"
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass
                try:
                    meta = indexing.client._read_meta() or {}
                    meta.pop(doc_id, None)
                    meta_path = indexing.client.workspace / "_meta.json"
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        finally:
            indexing.set_phase("idle")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    indexing.clear_cancel()

    return JSONResponse(content=UploadResponse(results=results).model_dump())
