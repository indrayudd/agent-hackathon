"""Story router: fetch, export, and regenerate the narrative story."""
from __future__ import annotations

import datetime
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

import nbformat

from backend.services.session_manager import get_session_dir

_LOG = logging.getLogger(__name__)
router = APIRouter(tags=["story"])


def _load_story(session_id: str) -> dict:
    """Load story.json for a session, or raise 404."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    story_file = session_dir / "story.json"
    if not story_file.exists():
        raise HTTPException(status_code=404, detail="Story not generated yet")

    return json.loads(story_file.read_text())


def _story_to_markdown(story: dict) -> str:
    """Convert story JSON to markdown string."""
    lines = [f"# {story.get('title', 'EDA Report')}\n"]
    summary = story.get("executive_summary", "")
    if summary:
        lines.append(f"{summary}\n")
    for section in story.get("sections", []):
        lines.append(f"## {section.get('title', section.get('phase', ''))}\n")
        lines.append(f"{section.get('content', '')}\n")
    return "\n".join(lines)


@router.get("/story/{session_id}")
async def get_story(session_id: str, format: str = Query("json")):
    """Return the story in the requested format (json, md, pdf)."""
    story = _load_story(session_id)

    if format == "md":
        md = _story_to_markdown(story)
        return PlainTextResponse(md, media_type="text/markdown")

    if format == "pdf":
        try:
            import markdown as md_lib
            import weasyprint
            md_text = _story_to_markdown(story)
            html = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
            full_html = f"<html><head><style>body{{font-family:sans-serif;max-width:800px;margin:auto;padding:20px}}img{{max-width:100%}}pre{{background:#f5f5f5;padding:10px}}</style></head><body>{html}</body></html>"
            pdf_bytes = weasyprint.HTML(string=full_html).write_pdf()
            return Response(content=pdf_bytes, media_type="application/pdf")
        except ImportError:
            raise HTTPException(status_code=501, detail="PDF export requires weasyprint")

    # Default: return JSON
    return story


@router.post("/story/{session_id}/regenerate")
async def regenerate_story(session_id: str):
    """Re-read the current notebook and regenerate the story via LLM."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    nb_path = session_dir / "notebook.ipynb"
    if not nb_path.exists():
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Read notebook cells
    nb = nbformat.read(str(nb_path), as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code"]
    md_cells = [c for c in nb.cells if c.cell_type == "markdown"]

    # Build sections from markdown headings and their following code cells
    sections: list[dict] = []
    current_section: dict | None = None
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            # Start a new section from markdown
            heading = cell.source.split("\n")[0].lstrip("#").strip() or "Section"
            current_section = {
                "phase": heading,
                "title": heading,
                "content": cell.source,
                "cell_ids": [],
                "plots": [],
                "insights": [],
            }
            sections.append(current_section)
        elif cell.cell_type == "code" and current_section is not None:
            # Attach code cell outputs as context
            cell_id = cell.get("id", "")
            current_section["cell_ids"].append(cell_id)
            # Extract text outputs for summary
            for output in cell.get("outputs", []):
                text = output.get("text", "")
                if not text and "data" in output:
                    text = output["data"].get("text/plain", "")
                if text:
                    current_section["content"] += f"\n\nOutput:\n{text[:300]}"

    if not sections:
        # Fallback: one section per code cell
        for i, cell in enumerate(code_cells):
            sections.append({
                "phase": f"Cell {i+1}",
                "title": f"Analysis {i+1}",
                "content": cell.source[:200],
                "cell_ids": [],
            })

    # Generate executive summary via LLM
    narrative = ""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = get_chat_model()

        # Gather all section content for the LLM
        all_content = "\n\n".join(
            f"## {s['title']}\n{s['content'][:500]}" for s in sections
        )

        # Load agent state for dataset info if available
        state_path = session_dir / "agent_state.json"
        dataset_info = ""
        if state_path.exists():
            agent_state = json.loads(state_path.read_text())
            dataset_info = f"Dataset: {agent_state.get('row_count', '?')} rows x {agent_state.get('col_count', '?')} cols\nColumns: {', '.join(agent_state.get('numeric_cols', [])[:15])}\nTime column: {agent_state.get('time_col', 'N/A')}"

        # Find dataset filename
        uploads_dir = session_dir / "uploads"
        dataset_name = "dataset"
        if uploads_dir.is_dir():
            files = list(uploads_dir.iterdir())
            if files:
                dataset_name = files[0].name

        resp = llm.invoke([
            SystemMessage(content="Write 2-3 paragraphs of flowing prose for an EDA report executive summary. Describe: what the data contains, key patterns, notable anomalies, and recommended next steps. Be specific with numbers. Do NOT use bullet points."),
            HumanMessage(content=f"Dataset: {dataset_name}\n{dataset_info}\n\nNotebook sections:\n{all_content[:4000]}"),
        ])
        narrative = resp.content.strip()
    except Exception as exc:
        _LOG.warning("LLM narrative regeneration failed: %s", exc)
        # Fallback: concatenate section titles
        narrative = "Key findings: " + "; ".join(s["title"] for s in sections[:10])

    story_data = {
        "title": f"EDA Report: {dataset_name}",
        "executive_summary": narrative,
        "sections": sections,
        "generated_at": datetime.datetime.now().isoformat(),
    }

    story_path = session_dir / "story.json"
    story_path.write_text(json.dumps(story_data, default=str, indent=2))

    _LOG.info("Story regenerated for session %s: %d sections", session_id, len(sections))

    return story_data
