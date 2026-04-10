"""
indexing.py — PageIndex module loading, the shared PageIndexClient singleton,
page-extraction helpers, indexing-phase / cancel state, and the LLM semaphore.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from config import (
    INDEXER_MODEL,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    PAGEINDEX_DIR,
    VISION_EXTRACTION_PROMPT,
    VISION_INDEXING_PROMPT,
    WORKSPACE_DIR,
)

logger = logging.getLogger("pageindex_service")

# ---------------------------------------------------------------------------
# LLM serialisation semaphore
# One shared semaphore for ALL LLM work (indexing + queries) so vLLM never
# processes more than one heavy job at a time, regardless of type.
# Initialised in init_semaphore(), called from the FastAPI lifespan handler.
# ---------------------------------------------------------------------------
llm_semaphore: asyncio.Semaphore  # set by init_semaphore()

# Simple counters so /queue_status can report how many requests are waiting.
index_queue_depth: int = 0
query_queue_depth: int = 0


def init_semaphore() -> None:
    """Create the LLM semaphore.  Must be called inside an async context
    (i.e. from the FastAPI lifespan handler) so the semaphore is bound to
    the correct event loop.
    """
    global llm_semaphore  # noqa: PLW0603
    llm_semaphore = asyncio.Semaphore(1)


# ---------------------------------------------------------------------------
# Indexing-phase tracking (polled by GET /indexing_phase)
# ---------------------------------------------------------------------------
# Values: "idle" | "pageindex" | "page_extract" | "done"
indexing_phase: str = "idle"
indexing_phase_file: str = ""   # filename being processed, for the UI

# Set to True by POST /cancel_indexing.  The current document is allowed to
# finish completely, then indexing stops before the next document starts.
cancel_after_current: bool = False


def set_phase(phase: str, filename: str = "") -> None:
    global indexing_phase, indexing_phase_file  # noqa: PLW0603
    indexing_phase = phase
    indexing_phase_file = filename


def request_cancel() -> None:
    global cancel_after_current  # noqa: PLW0603
    cancel_after_current = True


def clear_cancel() -> None:
    global cancel_after_current  # noqa: PLW0603
    cancel_after_current = False


# ---------------------------------------------------------------------------
# Lazy-loaded PageIndex symbols
# ---------------------------------------------------------------------------
_page_index_main        = None
_ConfigLoader           = None
_get_document           = None
_get_document_structure = None
_get_page_content       = None

# The shared PageIndexClient instance — populated by load_pageindex_modules().
client: Any = None


def _ensure_pageindex_importable() -> None:
    repo_str = str(PAGEINDEX_DIR)
    if not PAGEINDEX_DIR.exists():
        raise RuntimeError(
            f"PageIndex repository not found at '{PAGEINDEX_DIR}'. "
            "Run setup.sh first, or set the PAGEINDEX_DIR env variable."
        )
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
        logger.info("Added '%s' to sys.path", repo_str)


def load_pageindex_modules() -> None:
    """Import PageIndex symbols and initialise the PageIndexClient.
    Called once from the FastAPI lifespan handler.
    """
    global _page_index_main, _ConfigLoader                            # noqa: PLW0603
    global _get_document, _get_document_structure, _get_page_content  # noqa: PLW0603
    global client                                                      # noqa: PLW0603

    _ensure_pageindex_importable()

    try:
        from pageindex.page_index import page_index_main   # type: ignore[import]
        from pageindex.utils import ConfigLoader            # type: ignore[import]
        from pageindex.retrieve import (                    # type: ignore[import]
            get_document,
            get_document_structure,
            get_page_content,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Could not import PageIndex modules: {exc}. "
            "Make sure the repository is cloned and its dependencies are installed."
        ) from exc

    _page_index_main        = page_index_main
    _ConfigLoader           = ConfigLoader
    _get_document           = get_document
    _get_document_structure = get_document_structure
    _get_page_content       = get_page_content

    from pageindex.client import PageIndexClient  # type: ignore[import]
    client = PageIndexClient(
        model=INDEXER_MODEL,
        workspace=str(WORKSPACE_DIR),
    )
    logger.info(
        "PageIndex modules loaded (model=%s, api_base=%s, workspace=%s, docs_loaded=%d)",
        INDEXER_MODEL, OPENAI_API_BASE, WORKSPACE_DIR, len(client.documents),
    )


# ---------------------------------------------------------------------------
# Synchronous indexing helpers (run in a thread-pool via run_in_executor)
# ---------------------------------------------------------------------------

def _is_scanned_pdf(pdf_path: str) -> bool:
    """Return True if the PDF has negligible extractable text (i.e. scanned)."""
    import pymupdf  # type: ignore[import]
    doc = pymupdf.open(pdf_path)
    total_chars = sum(len(page.get_text().strip()) for page in doc)
    num_pages = doc.page_count
    doc.close()
    avg_chars_per_page = total_chars / max(num_pages, 1)
    # If average extractable chars per page is below threshold → scanned
    result = avg_chars_per_page < _SCANNED_TEXT_THRESHOLD
    logger.info(
        "Scanned detection for '%s': avg_chars_per_page=%.1f → %s",
        pdf_path, avg_chars_per_page, "SCANNED" if result else "digital",
    )
    return result


def run_pageindex_sync(pdf_path: str, opts: dict[str, Any]) -> dict:
    """Run page_index_main synchronously.  Intended for thread-pool execution."""
    os.environ["OPENAI_API_BASE"] = OPENAI_API_BASE
    os.environ["OPENAI_API_KEY"]  = OPENAI_API_KEY

    pdf_parser = opts.pop("pdf_parser", "PyMuPDF")

    config_loader = _ConfigLoader()
    opt = config_loader.load({**opts, "model": INDEXER_MODEL})

    if hasattr(opt, "__dict__"):
        opt.__dict__["pdf_parser"] = pdf_parser
        opt.__dict__.setdefault("model", INDEXER_MODEL)
    else:
        opt["pdf_parser"] = pdf_parser
        opt.setdefault("model", INDEXER_MODEL)

    # ── Scanned PDF: inject vision-extracted text for tree building ────────
    # page_index_main always calls get_page_tokens() via PyPDF2 internally.
    # For scanned PDFs this returns empty text → Processing failed.
    # Monkey-patch get_page_tokens to return text extracted with the
    # structure-focused vision prompt (verbatim headings, no paraphrasing).
    _patch_restore = None
    if _is_scanned_pdf(pdf_path):
        logger.info(
            "Scanned PDF '%s' — pre-extracting via vision indexing prompt", pdf_path
        )
        vision_pages = extract_pages_llm_vision_indexing(pdf_path)

        import sys as _sys
        import litellm as _litellm  # type: ignore[import]
        import pageindex.utils as _piu  # type: ignore[import]
        import pageindex.page_index  # ensure module is in sys.modules
        _pip = _sys.modules["pageindex.page_index"]  # get the actual module, not the re-exported fn

        prebuilt = [
            (p["content"], _litellm.token_counter(model=INDEXER_MODEL, text=p["content"]))
            for p in vision_pages
        ]

        # page_index.py does `from .utils import *` so get_page_tokens is bound
        # directly in page_index's own namespace — must patch that binding too.
        _orig_utils      = _piu.get_page_tokens
        _orig_pip_tokens = getattr(_pip, "get_page_tokens", None)

        def _patched_get_page_tokens(pdf_path_arg, model=None, pdf_parser="PyPDF2"):
            return prebuilt

        _piu.get_page_tokens = _patched_get_page_tokens
        _pip.get_page_tokens = _patched_get_page_tokens

        def _patch_restore():
            _piu.get_page_tokens = _orig_utils
            if _orig_pip_tokens is not None:
                _pip.get_page_tokens = _orig_pip_tokens
            else:
                try:
                    del _pip.get_page_tokens
                except AttributeError:
                    pass
            logger.info("get_page_tokens patch restored")

    logger.info("Starting page_index_main for '%s' (pdf_parser=%s)", pdf_path, pdf_parser)
    try:
        return _page_index_main(pdf_path, opt)
    finally:
        if _patch_restore:
            _patch_restore()


def extract_pages_pymupdf(pdf_path: str) -> list[dict]:
    """Extract per-page text using PyMuPDF (fitz)."""
    import pymupdf  # type: ignore[import]

    doc = pymupdf.open(pdf_path)
    pages = [{"page": i + 1, "content": page.get_text() or ""} for i, page in enumerate(doc)]
    doc.close()
    logger.info("PyMuPDF extraction complete — %d pages extracted", len(pages))
    return pages


# ---------------------------------------------------------------------------
# PDF → image conversion
# ---------------------------------------------------------------------------

# Minimum character count to consider a page as having a real text layer.
# Pages with fewer characters are treated as scanned/image-only.
_SCANNED_TEXT_THRESHOLD = 50

# DPI for born-digital PDFs (text layer present). 200 is the sweet spot:
# sharp enough for small text, not so large that it balloons the base64 payload.
_DPI_DIGITAL = 200

# Scanned pages get higher DPI because the raster source image often has
# lower effective resolution after PDF embedding.
_DPI_SCANNED = 300


def _page_to_b64_jpeg(page: Any, dpi: int, sharpen: bool = False) -> str:  # noqa: ANN401
    """Render a PyMuPDF page to a JPEG base64 string.

    Steps:
      1. Render at `dpi` into an RGB pixmap (PyMuPDF).
      2. Optionally sharpen (for scanned pages with soft edges).
      3. Encode as JPEG quality=95 — 60-70 % smaller than PNG with no
         perceptible loss for text content.
      4. Return the base64 string ready for the image_url payload.
    """
    from PIL import Image, ImageFilter  # type: ignore[import]
    import pymupdf                      # type: ignore[import]

    scale = dpi / 72.0
    mat   = pymupdf.Matrix(scale, scale)
    pix   = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB, alpha=False)

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    if sharpen:
        # Unsharp mask: radius=1, percent=150, threshold=3
        # Tightens blurry scan edges without introducing ringing artefacts.
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, optimize=True, subsampling=0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def extract_pages_llm_vision(pdf_path: str) -> list[dict]:
    """Extract per-page text by rendering each PDF page as an image and
    sending it to the vision LLM.  Falls back to PyMuPDF for any page that
    fails.

    Pipeline per page
    -----------------
    1. Detect whether the page has a real text layer (born-digital) or is
       scanned/image-only.
    2. Choose DPI accordingly: 200 for digital, 300 for scanned.
    3. Apply unsharp-mask sharpening for scanned pages only.
    4. Encode as JPEG (quality 95) — significantly smaller payload than PNG.
    5. Send to vision LLM with VISION_EXTRACTION_PROMPT as system message
       and the image as the sole user turn content.
    6. On any exception, fall back to PyMuPDF text extraction for that page.
    """
    import litellm  # type: ignore[import]
    import pymupdf  # type: ignore[import]

    os.environ["OPENAI_API_BASE"] = OPENAI_API_BASE
    os.environ["OPENAI_API_KEY"]  = OPENAI_API_KEY

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    pages: list[dict] = []
    logger.info("LLM Vision extraction starting — %d pages in '%s'", total_pages, pdf_path)

    for i, page in enumerate(doc):
        page_num = i + 1
        logger.info("Vision LLM — page %d/%d", page_num, total_pages)
        try:
            # ── 1. Detect page type ───────────────────────────────────────
            raw_text   = page.get_text().strip()
            is_scanned = len(raw_text) < _SCANNED_TEXT_THRESHOLD

            # ── 2 & 3. Render to JPEG base64 ─────────────────────────────
            dpi     = _DPI_SCANNED if is_scanned else _DPI_DIGITAL
            img_b64 = _page_to_b64_jpeg(page, dpi=dpi, sharpen=is_scanned)

            logger.debug(
                "Vision LLM — page %d: %s, dpi=%d, b64_len=%d",
                page_num,
                "scanned" if is_scanned else "digital",
                dpi,
                len(img_b64),
            )

            # ── 4. Call vision LLM ────────────────────────────────────────
            response = litellm.completion(
                model=INDEXER_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_EXTRACTION_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_b64}",
                                },
                            },
                        ],
                    },
                ],
                temperature=0,
                max_tokens=4096,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            content = (response.choices[0].message.content or "").strip()
            logger.info(
                "Vision LLM — page %d/%d done (%d chars extracted, scanned=%s)",
                page_num, total_pages, len(content), is_scanned,
            )

        except Exception as exc:
            logger.warning(
                "LLM vision failed for page %d of '%s' [%s: %s] — falling back to PyMuPDF",
                page_num, pdf_path, type(exc).__name__, exc,
            )
            content = page.get_text() or ""

        pages.append({"page": page_num, "content": content})

    doc.close()
    logger.info("LLM Vision extraction complete — %d pages extracted", len(pages))
    return pages


def extract_pages_llm_vision_indexing(pdf_path: str) -> list[dict]:
    """Vision extraction specifically for tree building.

    Uses VISION_INDEXING_PROMPT which instructs the model to copy headings
    verbatim from the page — critical so verify_toc can find them by fuzzy
    match. The retrieval extraction (extract_pages_llm_vision) uses a
    separate content-density prompt optimised for query answering.
    """
    import litellm  # type: ignore[import]
    import pymupdf  # type: ignore[import]

    os.environ["OPENAI_API_BASE"] = OPENAI_API_BASE
    os.environ["OPENAI_API_KEY"]  = OPENAI_API_KEY

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    pages: list[dict] = []
    logger.info(
        "LLM Vision (indexing) extraction starting — %d pages in '%s'",
        total_pages, pdf_path,
    )

    for i, page in enumerate(doc):
        page_num = i + 1
        logger.info("Vision LLM (indexing) — page %d/%d", page_num, total_pages)
        try:
            raw_text   = page.get_text().strip()
            is_scanned = len(raw_text) < _SCANNED_TEXT_THRESHOLD
            dpi        = _DPI_SCANNED if is_scanned else _DPI_DIGITAL
            img_b64    = _page_to_b64_jpeg(page, dpi=dpi, sharpen=is_scanned)

            response = litellm.completion(
                model=INDEXER_MODEL,
                messages=[
                    {"role": "system", "content": VISION_INDEXING_PROMPT},
                    {"role": "user",   "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }}
                    ]},
                ],
                timeout=120,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning(
                "Vision LLM (indexing) failed page %d — falling back to PyMuPDF: %s",
                page_num, exc,
            )
            content = page.get_text() or ""

        pages.append({"page": page_num, "content": content})

    doc.close()
    logger.info(
        "LLM Vision (indexing) extraction complete — %d pages extracted", len(pages)
    )
    return pages


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def count_tree_nodes(structure: list) -> int:
    total = 0
    for node in structure:
        total += 1
        if node.get("nodes"):
            total += count_tree_nodes(node["nodes"])
    return total


def find_latest_log() -> str | None:
    logs_dir = Path("./logs")
    if not logs_dir.exists():
        return None
    files = sorted(logs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def read_log_safe(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []