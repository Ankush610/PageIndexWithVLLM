"""
main.py — FastAPI app factory.

Responsibilities (only):
  • Configure logging
  • Define the lifespan handler (semaphore init + PageIndex module load)
  • Register middleware
  • Mount static files and serve the UI
  • Include all route routers
  • Register the global exception handler
  • uvicorn entry-point

Everything else lives in config.py, indexing.py, query.py, or routes/.
"""

from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

import indexing
from config import HOST, PORT, UI_DIR
from routes import documents, ops, upload
from routes import query_route
from routes import projects as projects_route
from routes import pdf_page

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("pageindex_service")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    indexing.init_semaphore()
    indexing.load_pageindex_modules()
    projects_route.ensure_default_project()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PageIndex PDF Indexer",
    description=(
        "Wraps the open-source PageIndex library to produce hierarchical JSON "
        "tree structures from uploaded PDF files using a local vLLM server."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static UI assets
# ---------------------------------------------------------------------------
_ui_static = UI_DIR / "static"
if _ui_static.exists():
    app.mount("/static", StaticFiles(directory=str(_ui_static)), name="static")
    logger.info("Serving static files from '%s'", _ui_static)
else:
    logger.warning(
        "UI static directory not found at '%s' — run from the project root "
        "or set UI_DIR env variable.",
        _ui_static,
    )


@app.get("/", include_in_schema=False)
async def serve_ui():
    index_path = UI_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail=f"UI not found at {index_path}")
    return FileResponse(str(index_path))


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(upload.router)
app.include_router(documents.router)
app.include_router(projects_route.router)
app.include_router(query_route.router)
app.include_router(ops.router)
app.include_router(pdf_page.router)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception on %s: %s", request.url.path, exc, exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        reload=False,
    )
