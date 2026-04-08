"""Story generation and export service."""
from __future__ import annotations

import json
import pathlib
import logging

from src.reporting.plot_contract import normalize_plot_artifacts

_LOG = logging.getLogger(__name__)
SESSIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "sessions"


def get_story(session_id: str) -> dict | None:
    """Load story.json for a session."""
    p = SESSIONS_DIR / session_id / "story.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def get_story_markdown(session_id: str) -> str | None:
    """Load story.md for a session."""
    p = SESSIONS_DIR / session_id / "story.md"
    if not p.exists():
        # Fall back to generating from JSON
        story = get_story(session_id)
        if not story:
            return None
        return _story_to_markdown(story)
    return p.read_text()


def _story_to_markdown(story: dict) -> str:
    """Convert a story dict to markdown format."""
    lines = [f"# {story.get('title', 'EDA Report')}", "", story.get("executive_summary", ""), ""]
    for section in story.get("sections", []):
        lines.append(f"## {section.get('title', section.get('phase', ''))}")
        content = section.get("content", "") or section.get("prose", "")
        lines.append(content)
        plots = normalize_plot_artifacts(section.get("plots") or [])
        for plot in plots[:6]:
            family = plot.get("chart_family") or "unknown"
            intent = plot.get("semantic_intent") or "unknown"
            if plot.get("kind") == "image" and plot.get("source"):
                caption = plot.get("title") or section.get("title", "")
                if family != "unknown" or intent != "unknown":
                    caption = f"{caption} ({family}, {intent})".strip()
                lines.append(f"![{caption}]({plot.get('source')})")
            elif plot.get("source"):
                label = plot.get("title") or section.get("title", "")
                if family != "unknown" or intent != "unknown":
                    label = f"{label} [{family} / {intent}]".strip()
                lines.append(f"- {label}")
        lines.append("")
    return "\n".join(lines)


def export_pdf(session_id: str) -> bytes | None:
    """Export story as PDF. Returns bytes or None."""
    md = get_story_markdown(session_id)
    if not md:
        return None
    try:
        import markdown
        import weasyprint
        html = markdown.markdown(md, extensions=["tables", "fenced_code"])
        full_html = (
            f"<html><head><style>"
            f"body{{font-family:sans-serif;max-width:800px;margin:auto;padding:20px}}"
            f"img{{max-width:100%}}"
            f"pre{{background:#f5f5f5;padding:10px;overflow-x:auto}}"
            f"</style></head><body>{html}</body></html>"
        )
        pdf = weasyprint.HTML(string=full_html).write_pdf()
        return pdf
    except ImportError:
        _LOG.warning("weasyprint or markdown not installed, PDF export unavailable")
        return None
