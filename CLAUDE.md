# CLAUDE.md — Project Root

This is the root guide. Read this first, then read the focused CLAUDE.md in whichever subdirectory you are working in.

---

## What this project is

A FastAPI server that wraps the open-source `PageIndex` library to provide a browser-based RAG interface for PDFs. Users upload PDFs, the server indexes them into a hierarchical section tree using a local vLLM LLM, and the UI allows querying via an agent loop. No embeddings, no vector database, everything runs locally. **PDF only** — txt/md are not supported (users convert to PDF first).

---

## Focused guides — read these when working in specific areas

| Directory | CLAUDE.md covers |
|---|---|
| `routes/CLAUDE.md` | All API endpoints, request/response shapes, error handling patterns |
| `PageIndex/CLAUDE.md` | What we changed vs original library, the monkey-patch, strict DO NOT TOUCH rules |
| `ui/CLAUDE.md` | UI architecture, JS globals, CSS variables, PDF panel, page chip system |

---

## Project layout

```
├── main.py               ← FastAPI app factory ONLY — lifespan, middleware, routers, entry-point
├── config.py             ← ALL env/path constants, PAGEINDEX_OPTS_DEFAULT, prompt loading
├── indexing.py           ← PageIndexClient singleton, LLM semaphore, run_pageindex_sync(),
│                            scanned PDF detection, vision extractors, phase/cancel tracking
├── query.py              ← run_query_sync() — the agent RAG loop + system prompt
├── models/               ← Pydantic models for every JSON boundary (never use raw dicts)
├── routes/               ← FastAPI routers, one file per concern, no business logic here
├── ui/                   ← Browser frontend (index.html, app.css, app.js)
├── prompts/              ← LLM prompt text files loaded by config.py
│   ├── vision_extraction.txt   ← used for retrieval-layer page extraction
│   └── vision_indexing.txt     ← used for tree-building extraction (scanned PDFs)
├── PageIndex/            ← Third-party library — see PageIndex/CLAUDE.md
├── workspace/            ← Runtime-generated: PDFs, JSON trees, _meta.json
└── logs/                 ← Runtime-generated: PageIndex JSON logs
```

---

## HARD CONSTRAINTS — never violate these

### 1. Never modify `PageIndex/pageindex/` except the two files we own
We modified `utils.py` and `client.py` for vLLM compatibility. Everything else (`page_index.py`, `retrieve.py`, `page_index_md.py`, `config.yaml`) is untouched original library code — do not touch.

### 2. Never pass unknown keys to `ConfigLoader.load()`
Valid keys only:
```
model, retrieve_model, toc_check_page_num, max_page_num_each_node,
max_token_num_each_node, if_add_node_id, if_add_node_summary,
if_add_doc_description, if_add_node_text
```
`pdf_parser` is NOT valid — pop it before `config_loader.load()`, stamp it onto opt after. See `run_pageindex_sync()`.

### 3. Never set `if_add_node_text` to `"yes"` in defaults
Bloats every LLM call with full page text and causes `max_output_reached`.

### 4. `doc_name` must always be the original upload filename
UI polls `/documents` matching `d.doc_name === fname`. Using temp path breaks this and hangs the UI forever. Always use `filename` (from `file.filename`).

### 5. Always use `shutil.copyfile`, never `shutil.copy2`
`copy2` fails with `PermissionError` on NTFS/WSL paths.

### 6. `toc_check_page_num` must default to `0`
Values above 0 reliably hit `max_output_reached` on longer documents.

### 7. Never change `llm_semaphore` from `Semaphore(1)`
Serialises ALL LLM work. Increasing it causes KV-cache eviction and retry storms on vLLM.

### 8. Always reset `indexing_phase` to `"idle"` in the `finally` block
Skipping this permanently freezes the UI overlay.

---

## Module responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | App factory only — lifespan, middleware, routers, static files, entry-point |
| `config.py` | Env vars, path constants, `PAGEINDEX_OPTS_DEFAULT`, `CONFIGLOADER_KEYS`, prompt loading |
| `indexing.py` | PageIndex imports, `client` singleton, `llm_semaphore`, phase/cancel state, sync helpers, vision/pymupdf extractors |
| `query.py` | `run_query_sync()` and `_QUERY_SYSTEM_PROMPT` only |
| `routes/*.py` | HTTP routing only — delegates to indexing/query, no business logic |

---

## `client.documents` — central state

`indexing.client` is the `PageIndexClient` singleton. Key fields per document:
- `doc_id` — UUID string
- `doc_name` — original upload filename
- `type` — always `"pdf"`
- `path` — absolute path to `workspace/<doc_id>.pdf`
- `structure` — section tree (None if lazy-loaded)
- `pages` — list of `{"page": int, "content": str}` (absent if lazy-loaded)
- `page_count`, `total_nodes`, `project`

After `_save_doc()`, `structure` and `pages` are stripped from memory and reloaded on demand by `_ensure_doc_loaded()`.

---

## Scanned PDF pipeline

1. `_is_scanned_pdf()` — avg chars/page < 50 → scanned
2. `extract_pages_llm_vision_indexing()` runs using `VISION_INDEXING_PROMPT` — outputs `#`/`##`/`###` headings so PageIndex's `verify_toc` fuzzy-match works
3. Result injected via monkey-patch on `get_page_tokens` in BOTH `pageindex.utils` AND `pageindex.page_index` (wildcard import creates its own binding — patch both or the original still runs)
4. Use `sys.modules["pageindex.page_index"]` to get the real module — `import pageindex.page_index as _pip` gives the re-exported function from `__init__.py`, not the module
5. Patch always restored in `finally`

---

## PAGEINDEX_OPTS_DEFAULT

```python
{
    "toc_check_page_num":      0,         # must stay 0
    "max_page_num_each_node":  5,
    "max_token_num_each_node": 4000,
    "if_add_node_summary":     "no",
    "if_add_node_id":          "yes",     # must stay "yes"
    "if_add_node_text":        "no",      # must stay "no"
    "if_add_doc_description":  "no",
    "pdf_parser":              "PyMuPDF"  # popped before ConfigLoader.load()
}
```

---

## Common errors

| Error | Cause |
|---|---|
| `ValueError: Unknown config keys: {'pdf_parser'}` | `pdf_parser` passed to `ConfigLoader.load()` |
| `finish reason: max_output_reached` | `toc_check_page_num > 0` |
| UI hangs after indexing | `doc_name` set to temp path |
| `PermissionError: [Errno 1]` | Running from `/mnt/c/` on WSL |
| `Processing failed` | Scanned PDF — vision pipeline handles this automatically |
| `AttributeError: 'function' object has no attribute 'verify_toc'` | `_pip` resolved to function — use `sys.modules["pageindex.page_index"]` |
