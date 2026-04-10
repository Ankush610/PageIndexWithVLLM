"""
config.py — Environment variables, path constants, default indexing opts,
and prompt loading.  No imports from other project modules.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env (shell env always wins)
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

logger = logging.getLogger("pageindex_service")

# ---------------------------------------------------------------------------
# Environment / configuration
# ---------------------------------------------------------------------------
OPENAI_API_BASE: str  = os.environ.setdefault("OPENAI_API_BASE", "http://localhost:8000/v1")
OPENAI_API_KEY: str   = os.environ.setdefault("OPENAI_API_KEY",  "vllm")
INDEXER_MODEL: str    = os.environ.get("INDEXER_MODEL", "openai/qwen2.5-72b")
MAX_UPLOAD_MB: int    = int(os.environ.get("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

PAGEINDEX_DIR: Path  = Path(os.environ.get("PAGEINDEX_DIR",  "./PageIndex")).resolve()
UI_DIR: Path         = Path(os.environ.get("UI_DIR",         "./ui")).resolve()
WORKSPACE_DIR: Path  = Path(os.environ.get("WORKSPACE_DIR",  "./workspace")).resolve()
PROMPTS_DIR: Path    = Path(os.environ.get("PROMPTS_DIR",    "./prompts")).resolve()

HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "8080"))

# ---------------------------------------------------------------------------
# Default PageIndex indexing options
# ---------------------------------------------------------------------------
PAGEINDEX_OPTS_DEFAULT: dict[str, Any] = {
    "toc_check_page_num":       0,
    "max_page_num_each_node":   5,
    "max_token_num_each_node":  4000,
    "if_add_node_summary":      "no",
    "if_add_node_id":           "yes",
    "if_add_node_text":         "no",
    "if_add_doc_description":   "no",
    "pdf_parser":               "PyMuPDF",
}

# Keys that ConfigLoader accepts (used to filter UI settings before passing)
CONFIGLOADER_KEYS: frozenset[str] = frozenset({
    "toc_check_page_num",
    "max_page_num_each_node",
    "max_token_num_each_node",
    "if_add_node_summary",
    "if_add_node_id",
    "if_add_node_text",
    "if_add_doc_description",
})

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------
def _load_prompt(filename: str) -> str:
    """Load a prompt from the prompts/ directory.

    Logs a warning and returns a minimal fallback string if the file is
    missing, so the vision pipeline degrades gracefully rather than crashing.
    """
    path = PROMPTS_DIR / filename
    try:
        text = path.read_text(encoding="utf-8").strip()
        logger.info("Loaded prompt '%s' (%d chars)", filename, len(text))
        return text
    except OSError:
        logger.warning(
            "Prompt file '%s' not found at '%s' — using bare fallback prompt. "
            "Make sure the prompts/ directory exists relative to the project root.",
            filename, path,
        )
        return (
            "Extract all text from this PDF page exactly as it appears. "
            "Preserve headings, bullet points, tables, and paragraph structure. "
            "Output only the extracted text."
        )


# Loaded once at module level — ready before any upload request arrives.
VISION_EXTRACTION_PROMPT: str = _load_prompt("vision_extraction.txt")
VISION_INDEXING_PROMPT:   str = _load_prompt("vision_indexing.txt")
