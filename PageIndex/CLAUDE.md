# CLAUDE.md — PageIndex/

This directory contains the PageIndex open-source library. The subdirectory structure is:

```
PageIndex/
├── CLAUDE.md              ← this file
├── run_pageindex.py       ← CLI entry-point for the library (not used by our service)
└── pageindex/             ← the actual library package
    ├── page_index.py      ← core indexing engine — DO NOT MODIFY
    ├── page_index_md.py   ← markdown indexer — not used, do not modify
    ├── utils.py           ← LLM call helpers — MODIFIED (see below)
    ├── client.py          ← workspace client — MODIFIED (see below)
    ├── retrieve.py        ← page content retrieval — MODIFIED (see below)
    ├── config.yaml        ← ConfigLoader schema — DO NOT MODIFY
    └── __init__.py        ← re-exports via wildcard — DO NOT MODIFY
```

---

## Files we modified vs original

### `pageindex/utils.py` — vLLM compatibility

Two LLM call sites (`llm_completion` and `llm_acompletion`) have these params added:
```python
max_tokens=16384,
extra_body={"chat_template_kwargs": {"enable_thinking": False}},
```
This disables chain-of-thought thinking mode on Qwen3 models and sets a token budget. Without `enable_thinking: False`, Qwen3 produces extended internal reasoning which bloats output and may hit limits.

### `pageindex/client.py` — PDF-only, project field

- Removed all markdown (`md_to_tree`) support — PDF only
- Removed `is_md` detection, `md` branch in `index()`
- `_make_meta_entry()` simplified — no `line_count`, always `type: "pdf"`
- Added `'project': doc.get('project', 'default')` to meta entries

### `pageindex/retrieve.py` — PDF-only

- Removed `_get_md_page_content()` function
- Removed md branch from `get_page_content()`
- Removed `line_count` from `get_document()` response
- `type` is always `"pdf"` now

---

## Files we do NOT modify — ever

### `pageindex/page_index.py`

The core indexing engine. Contains `page_index_main()`, `verify_toc()`, `meta_processor()`, `generate_toc_init()`, all tree-building logic.

**Never touch this file.** All our scanned PDF handling is done via monkey-patching from `indexing.py` in the parent project.

### `pageindex/config.yaml`

Defines valid `ConfigLoader` keys. Our service reads this schema. Adding or changing keys here would require matching changes in `config.py`. Do not touch.

### `pageindex/__init__.py`

Does `from .page_index import *` — this wildcard import is the reason we must use `sys.modules["pageindex.page_index"]` instead of `import pageindex.page_index as _pip` when monkey-patching. The wildcard import creates local bindings in the module's namespace; patching the module attribute only is not enough.

---

## The monkey-patch — why and how

**Problem:** `page_index_main()` calls `get_page_tokens(doc, model)` internally to extract text from PDFs. For scanned PDFs this returns empty/garbage text, causing `meta_processor` to fail with `Exception('Processing failed')`.

**Solution:** Before calling `page_index_main()`, we replace `get_page_tokens` with a function that returns our vision-extracted text instead.

**The wildcard import trap:** `page_index.py` starts with `from .utils import *`. This copies `get_page_tokens` into `page_index`'s own module namespace as a local binding at import time. Patching `pageindex.utils.get_page_tokens` only patches the utils module — the already-bound name in `page_index`'s namespace still points to the original function.

**The fix (in `indexing.py`):**
```python
import pageindex.page_index           # ensure in sys.modules
_pip = sys.modules["pageindex.page_index"]   # get actual module object

_pip.get_page_tokens = _patched_fn    # patch the local binding
_piu.get_page_tokens = _patched_fn    # patch utils too (belt and suspenders)
```

Using `import pageindex.page_index as _pip` would give the re-exported `page_index_main` function (from `__init__.py`'s wildcard), not the module. `sys.modules` is the only reliable way.

**Restore:** Always in a `finally` block in `run_pageindex_sync()`.

---

## Vision prompt format requirement

`vision_indexing.txt` (in `prompts/`) must output headings as markdown (`#`, `##`, `###`), NOT as `H1:`, `H2:`, `H3:`.

Why: `generate_toc_init()` in `page_index.py` extracts titles from the page text and `verify_toc()` fuzzy-matches those titles back against the page text. The official PageIndex site uses markdown headings. If the format differs, `verify_toc` returns accuracy ≤ 0.6 → `meta_processor` raises `Processing failed`.

---

## What NOT to do

- Do not call `client.index()` — it hardcodes opts and doesn't support our configurable settings. We call `page_index_main()` directly.
- Do not add `pdf_parser` to `config.yaml` — it's intentionally kept out and handled specially.
- Do not increase `max_tokens` in `utils.py` above 16384 without testing — larger values stress vLLM's KV cache on the available GPU.
