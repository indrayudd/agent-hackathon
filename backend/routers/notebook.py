"""Notebook router: read, update, and confirm notebooks."""
from __future__ import annotations

import json

import nbformat
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.session_manager import get_session_dir

router = APIRouter(tags=["notebook"])


class NotebookPatchBody(BaseModel):
    """Body for PATCH /notebook/{session_id}."""

    cells: list[dict]


@router.get("/notebook/{session_id}")
async def get_notebook(session_id: str):
    """Return the notebook.ipynb from the session directory as JSON."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    nb_path = session_dir / "notebook.ipynb"
    if not nb_path.exists():
        raise HTTPException(status_code=404, detail="Notebook not found for this session")

    nb = nbformat.read(str(nb_path), as_version=4)
    return json.loads(nbformat.writes(nb))


@router.patch("/notebook/{session_id}")
async def patch_notebook(session_id: str, body: NotebookPatchBody):
    """Overwrite notebook.ipynb with the provided cell list."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    nb = nbformat.v4.new_notebook()
    for cell_data in body.cells:
        cell_type = cell_data.get("cell_type", "code")
        source = cell_data.get("source", "")
        if cell_type == "markdown":
            nb.cells.append(nbformat.v4.new_markdown_cell(source))
        else:
            nb.cells.append(nbformat.v4.new_code_cell(source))

    nb_path = session_dir / "notebook.ipynb"
    nbformat.write(nb, str(nb_path))

    return {"status": "updated", "cell_count": len(nb.cells)}


@router.post("/notebook/{session_id}/confirm")
async def confirm_notebook(session_id: str):
    """Placeholder: confirm the current notebook version."""
    try:
        get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {"status": "confirmed", "version_id": 1}
