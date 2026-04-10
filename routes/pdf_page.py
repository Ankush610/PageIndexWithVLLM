"""
routes/pdf_page.py — Render a single PDF page as a JPEG image.

GET /pdf/{doc_id}/page/{page_num}

Used by the UI to show the source PDF page when a citation chip is clicked.
Renders the requested page at 150 DPI and returns it as image/jpeg.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import indexing
from config import WORKSPACE_DIR

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["pdf"])

_DPI = 150  # good balance: readable text, small payload (~100-200 KB per page)


@router.get("/pdf/{doc_id}/page/{page_num}")
async def get_pdf_page_image(doc_id: str, page_num: int) -> Response:
    """Render a single PDF page as a JPEG and return it."""
    if not indexing.client or doc_id not in indexing.client.documents:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    pdf_path = WORKSPACE_DIR / f"{doc_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk.")

    try:
        import pymupdf  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        doc = pymupdf.open(str(pdf_path))
        total = len(doc)

        if page_num < 1 or page_num > total:
            raise HTTPException(
                status_code=400,
                detail=f"Page {page_num} out of range (document has {total} pages).",
            )

        page = doc[page_num - 1]
        scale = _DPI / 72.0
        mat = pymupdf.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB, alpha=False)
        doc.close()

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90, optimize=True)
        buf.seek(0)

        return Response(
            content=buf.read(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to render page %d of '%s': %s", page_num, doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Render error: {exc}") from exc
