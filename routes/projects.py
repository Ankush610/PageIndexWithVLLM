"""
routes/projects.py — Project (directory) management endpoints.

Projects are logical groupings stored in workspace/_projects.json.
Each document can belong to exactly one project; "default" is always present.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import WORKSPACE_DIR

logger = logging.getLogger("pageindex_service")

router = APIRouter(tags=["projects"])

PROJECTS_FILE: Path = WORKSPACE_DIR / "_projects.json"
DEFAULT_PROJECT = "default"


# ── helpers ────────────────────────────────────────────────────────────────────

def _read_projects() -> list[str]:
    """Return sorted list of project names, always including 'default'."""
    try:
        if PROJECTS_FILE.exists():
            data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
            projects = data if isinstance(data, list) else []
        else:
            projects = []
    except Exception:
        projects = []
    if DEFAULT_PROJECT not in projects:
        projects = [DEFAULT_PROJECT] + [p for p in projects if p != DEFAULT_PROJECT]
    return projects


def _write_projects(projects: list[str]) -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    if DEFAULT_PROJECT not in projects:
        projects = [DEFAULT_PROJECT] + projects
    PROJECTS_FILE.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_doc_projects() -> dict[str, str]:
    """Return mapping of doc_id → project name from workspace/_meta.json."""
    meta_path = WORKSPACE_DIR / "_meta.json"
    try:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return {doc_id: (entry.get("project") or DEFAULT_PROJECT) for doc_id, entry in meta.items()}
    except Exception:
        pass
    return {}


def _write_doc_project(doc_id: str, project: str) -> None:
    """Update the project field of a single doc in _meta.json."""
    meta_path = WORKSPACE_DIR / "_meta.json"
    try:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {}
        if doc_id in meta:
            meta[doc_id]["project"] = project
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        # Also update the individual doc JSON
        doc_path = WORKSPACE_DIR / f"{doc_id}.json"
        if doc_path.exists():
            doc = json.loads(doc_path.read_text(encoding="utf-8"))
            doc["project"] = project
            doc_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to update project for doc %s: %s", doc_id, e)


def ensure_default_project() -> None:
    """Called at startup — make sure 'default' project exists."""
    projects = _read_projects()
    _write_projects(projects)


# ── request bodies ──────────────────────────────────────────────────────────────

class CreateProjectBody(BaseModel):
    name: str

class RenameProjectBody(BaseModel):
    new_name: str

class MoveDocBody(BaseModel):
    project: str


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects() -> JSONResponse:
    """Return all project names."""
    return JSONResponse(content={"projects": _read_projects()})


@router.post("/projects")
async def create_project(body: CreateProjectBody) -> JSONResponse:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    projects = _read_projects()
    if name in projects:
        raise HTTPException(status_code=409, detail=f"Project '{name}' already exists.")
    projects.append(name)
    _write_projects(projects)
    return JSONResponse(content={"status": "created", "name": name})


@router.patch("/projects/{name}")
async def rename_project(name: str, body: RenameProjectBody) -> JSONResponse:
    if name == DEFAULT_PROJECT:
        raise HTTPException(status_code=400, detail="Cannot rename the default project.")
    new_name = body.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty.")
    projects = _read_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")
    if new_name in projects:
        raise HTTPException(status_code=409, detail=f"Project '{new_name}' already exists.")
    projects = [new_name if p == name else p for p in projects]
    _write_projects(projects)
    # Update all docs that belong to this project — both disk and in-memory
    import indexing
    meta_path = WORKSPACE_DIR / "_meta.json"
    try:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            changed = False
            for doc_id, entry in meta.items():
                if entry.get("project") == name:
                    entry["project"] = new_name
                    changed = True
                    # Also update in-memory so GET /documents reflects change immediately
                    if indexing.client and doc_id in indexing.client.documents:
                        indexing.client.documents[doc_id]["project"] = new_name
            if changed:
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to migrate docs on rename: %s", e)
    return JSONResponse(content={"status": "renamed", "name": new_name})


@router.delete("/projects/{name}")
async def delete_project(name: str) -> JSONResponse:
    """Delete a project and all its documents."""
    import indexing
    if name == DEFAULT_PROJECT:
        raise HTTPException(status_code=400, detail="Cannot delete the default project.")
    projects = _read_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found.")

    # Find and delete all docs in this project
    doc_projects = _read_doc_projects()
    docs_to_delete = [doc_id for doc_id, proj in doc_projects.items() if proj == name]

    if indexing.client:
        meta_path = WORKSPACE_DIR / "_meta.json"
        meta = {}
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

        for doc_id in docs_to_delete:
            indexing.client.documents.pop(doc_id, None)
            for suffix in (".pdf", ".json"):
                p = WORKSPACE_DIR / f"{doc_id}{suffix}"
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            meta.pop(doc_id, None)

        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    projects = [p for p in projects if p != name]
    _write_projects(projects)
    return JSONResponse(content={"status": "deleted", "name": name, "docs_removed": len(docs_to_delete)})


@router.post("/document/{doc_id}/move")
async def move_document(doc_id: str, body: MoveDocBody) -> JSONResponse:
    """Move a document to a different project."""
    import indexing
    if not indexing.client or doc_id not in indexing.client.documents:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    projects = _read_projects()
    if body.project not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{body.project}' not found.")

    # Update in-memory — GET /documents reads this directly
    indexing.client.documents[doc_id]["project"] = body.project

    # Persist via _save_meta. Now that _make_meta_entry includes 'project',
    # this single call is the complete persistence path — survives restarts.
    try:
        meta_entry = indexing.client._make_meta_entry(indexing.client.documents[doc_id])
        indexing.client._save_meta(doc_id, meta_entry)
    except Exception as e:
        logger.warning("Failed to persist project move for %s: %s", doc_id, e)

    return JSONResponse(content={"status": "moved", "doc_id": doc_id, "project": body.project})
