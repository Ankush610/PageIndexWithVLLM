# CLAUDE.md — routes/

This directory contains all FastAPI routers. Each file is one concern. No business logic lives here — routes receive requests, validate with Pydantic, delegate to `indexing.py` or `query.py`, and return responses.

---

## Files

| File | Endpoints | Delegates to |
|---|---|---|
| `upload.py` | `POST /upload` | `indexing.run_pageindex_sync()`, `indexing.extract_pages_*()` |
| `documents.py` | `GET /documents`, `DELETE /document/{doc_id}` | `indexing.client.documents` |
| `query_route.py` | `POST /query` | `query.run_query_sync()` |
| `ops.py` | `GET /health`, `/log_latest`, `/indexing_phase`, `/queue_status`, `POST /cancel_indexing` | `indexing.*` state vars |
| `pdf_page.py` | `GET /pdf/{doc_id}/page/{page_num}` | PyMuPDF directly |
| `projects.py` | Project CRUD endpoints | `indexing.client.documents` |

---

## POST /upload

**File:** `upload.py`

Accepts multipart: `files[]` (PDF only) + `settings` (JSON string → `UploadSettings`).

Flow per file:
1. Validate extension (`.pdf` only), size, PDF magic bytes
2. Write to `/tmp/<uuid>.pdf`
3. Acquire `llm_semaphore` (blocks all other LLM work)
4. `_is_scanned_pdf()` → detect scanned
5. `run_pageindex_sync(tmp_path, opts)` in thread-pool → builds section tree
6. `extract_pages_llm_vision()` or `extract_pages_pymupdf()` → page text for retrieval
7. `shutil.copyfile(tmp → workspace/<doc_id>.pdf)` — always `copyfile` not `copy2`
8. Populate `client.documents[doc_id]` with `doc_name = filename` (original name, not temp)
9. `client._save_doc(doc_id)` → persists to disk
10. `os.unlink(tmp_path)` in `finally`

**Critical:** `doc_name` must be the original `file.filename`. The UI polls `/documents` matching on `d.doc_name === fname`. Wrong name = UI hangs forever.

**Error cleanup:** If exception after `doc_id` is assigned — remove from `client.documents`, delete workspace files, rewrite `_meta.json`.

**Settings merging:** Only keys in `CONFIGLOADER_KEYS` from `UploadSettings` are passed to `opts`. `use_llm_parser` is extracted separately and never passed to `ConfigLoader`.

---

## POST /query

**File:** `query_route.py` (named to avoid shadowing the `query` module)

Accepts `QueryRequest` (`query`, `doc_id` or `doc_ids`). Validates doc IDs exist in `client.documents`. Acquires `llm_semaphore`, runs `run_query_sync()` in thread-pool, returns `QueryResponse`.

---

## GET /pdf/{doc_id}/page/{page_num}

**File:** `pdf_page.py`

Renders a single PDF page as JPEG using PyMuPDF at 150 DPI. Used by the UI PDF panel when a source chip is clicked. Returns `image/jpeg` with 1-hour cache header. Validates doc exists and page number is in range.

---

## GET /documents

Returns all docs from `client.documents` as `DocumentsResponse`. Includes `doc_id`, `doc_name`, `page_count`, `total_nodes`, `project`.

---

## DELETE /document/{doc_id}

Removes from `client.documents`, deletes `workspace/<doc_id>.pdf` and `.json`, rewrites `_meta.json`.

---

## GET /indexing_phase

Returns `{"phase": str, "file": str}`. Phase values: `"idle"` | `"pageindex"` | `"page_extract"` | `"done"`. Polled by UI overlay every 1.8s to show correct progress step.

---

## GET /queue_status

Returns `{"index_busy": bool, "index_waiting": int, "query_busy": bool, "query_waiting": int}`. UI uses this to show the "Queued" banner and to gate sending the next file upload.

---

## Pydantic models (from `models/`)

| Model | Used in |
|---|---|
| `UploadSettings` | `POST /upload` settings — `extra="ignore"` drops unknown UI keys |
| `UploadFileResult`, `UploadResponse` | `POST /upload` response |
| `QueryRequest` | `POST /query` request |
| `QueryResponse`, `TraversalStep`, `ContextPassage` | `POST /query` response |
| `DocumentSummary`, `DocumentsResponse` | `GET /documents` response |
| `DeleteResponse` | `DELETE /document/{doc_id}` response |
| `HealthResponse` | `GET /health` response |

Never use raw `dict` for API boundaries — always go through the models.

---

## LLM semaphore pattern

Both `/upload` and `/query` acquire `indexing.llm_semaphore` before doing any LLM work:

```python
async with indexing.llm_semaphore:
    indexing.query_queue_depth -= 1
    result = await asyncio.get_event_loop().run_in_executor(None, run_query_sync, ...)
```

This is intentional — it enforces serial execution of all LLM jobs. Do not remove or work around it.
