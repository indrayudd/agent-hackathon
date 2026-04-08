"""Story router: fetch, export, and regenerate the narrative story."""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import io
import unicodedata
import textwrap
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

import nbformat

from backend.services.session_manager import get_session_dir
from src.reporting.plot_contract import (
    build_report_viz_spec,
    infer_plot_semantics,
    plot_artifacts_from_outputs,
    plot_specs_by_cell,
)

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


def _default_plot_display(plot_type: str, index: int = 0) -> dict[str, Any]:
    if plot_type == "plotly":
        return {
            "width": 960,
            "height": 540,
            "aspect_ratio": 960 / 540,
            "fit": "contain",
            "max_width": 960,
            "max_height": 540,
            "slot": index + 1,
        }
    return {
        "width": 960,
        "height": 540,
        "aspect_ratio": 960 / 540,
        "fit": "contain",
        "max_width": 960,
        "max_height": 540,
        "slot": index + 1,
    }


def _clean_base64_payload(value: str) -> str:
    return value.replace("\n", "").replace("\r", "").replace(" ", "")


def _coerce_dimension(value: Any) -> int | None:
    try:
        if value is None:
            return None
        numeric = int(float(value))
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return max(240, min(numeric, 1600))


def _frame_from_dimensions(plot_type: str, width: int | None, height: int | None, index: int = 0) -> dict[str, Any]:
    frame = _default_plot_display(plot_type, index)
    if width and height:
        ratio = max(1.1, min(width / height, 2.1))
        frame["aspect_ratio"] = ratio
        frame["height"] = max(300, min(height, 540))
        frame["width"] = max(320, min(width, 960))
        frame["native_width"] = width
        frame["native_height"] = height
    return frame


def _normalize_plotly_payload(payload: Any, index: int = 0) -> tuple[str, dict[str, Any]]:
    try:
        parsed = json.loads(payload) if isinstance(payload, str) else dict(payload or {})
    except Exception:
        return str(payload), _default_plot_display("plotly", index)

    layout = parsed.get("layout") or {}
    if not isinstance(layout, dict):
        layout = {}
        parsed["layout"] = layout

    width = _coerce_dimension(layout.pop("width", None))
    height = _coerce_dimension(layout.pop("height", None))
    frame = _frame_from_dimensions("plotly", width, height, index)

    layout["autosize"] = True
    layout["paper_bgcolor"] = "rgba(0,0,0,0)"
    layout["plot_bgcolor"] = "rgba(0,0,0,0)"
    if not isinstance(layout.get("margin"), dict):
        layout["margin"] = {"t": 28, "r": 20, "b": 52, "l": 60}

    return json.dumps(parsed), frame


def _image_frame_from_output_metadata(metadata: Any, index: int = 0) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return _default_plot_display("image", index)

    image_meta = metadata.get("image/png")
    width = None
    height = None
    if isinstance(image_meta, dict):
        width = _coerce_dimension(image_meta.get("width"))
        height = _coerce_dimension(image_meta.get("height"))

    width = width or _coerce_dimension(metadata.get("width"))
    height = height or _coerce_dimension(metadata.get("height"))
    return _frame_from_dimensions("image", width, height, index)


def _normalize_plot_entry(
    plot: Any,
    *,
    section: dict[str, Any],
    cell_id: str | None = None,
    index: int = 0,
) -> dict[str, Any]:
    title = section.get("visual_title") or section.get("title") or section.get("phase") or "Figure"
    caption = section.get("visual_caption") or ""

    if isinstance(plot, dict):
        normalized = dict(plot)
        source = normalized.get("source") or normalized.get("payload") or normalized.get("path") or ""
        plot_kind = str(normalized.get("kind") or normalized.get("type") or "image").strip().lower()
        display = normalized.get("display") or normalized.get("frame")

        if plot_kind == "plotly":
            source, display_from_source = _normalize_plotly_payload(source, index)
            display = display or display_from_source
        else:
            source = str(source)
            if source and not source.startswith("http") and not source.startswith("data:"):
                cleaned = _clean_base64_payload(source)
                if len(cleaned) > 120 and re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
                    source = f"data:image/png;base64,{cleaned}"
            display = display or _default_plot_display("image", index)

        normalized["kind"] = "plotly" if plot_kind == "plotly" else "image"
        normalized["mime_type"] = normalized.get("mime_type") or (
            "application/vnd.plotly.v1+json" if normalized["kind"] == "plotly" else "image/png"
        )
        normalized["source"] = source
        normalized["title"] = normalized.get("title") or title
        normalized["caption"] = normalized.get("caption") or caption
        normalized["source_cell_id"] = normalized.get("source_cell_id") or cell_id or ""
        normalized["display"] = display
        semantic = infer_plot_semantics(
            normalized["kind"],
            str(source),
            title=str(normalized["title"]),
            caption=str(normalized["caption"]),
        )
        for field in ("chart_family", "semantic_intent", "x_axis_role", "y_axis_role", "semantic_confidence"):
            if normalized.get(field) in (None, "", "unknown"):
                normalized[field] = semantic[field]
        normalized["viz_spec"] = build_report_viz_spec(normalized).model_dump()
        normalized.pop("payload", None)
        normalized.pop("frame", None)
        return normalized

    raw = str(plot).strip()
    if not raw:
        return {
            "kind": "image",
            "mime_type": "image/png",
            "source": "",
            "title": title,
            "caption": caption,
            "source_cell_id": cell_id or "",
            "display": _default_plot_display("image", index),
            "viz_spec": build_report_viz_spec(
                {
                    "kind": "image",
                    "source": "",
                    "title": title,
                    "caption": caption,
                    "display": _default_plot_display("image", index),
                    "chart_family": "image",
                    "semantic_intent": "unknown",
                    "x_axis_role": "unknown",
                    "y_axis_role": "unknown",
                    "semantic_confidence": 1.0,
                }
            ).model_dump(),
        }

    if raw.startswith("http") or raw.startswith("data:"):
        semantic = infer_plot_semantics("image", raw, title=title, caption=caption)
        return {
            "kind": "image",
            "mime_type": "image/png",
            "source": raw,
            "title": title,
            "caption": caption,
            "source_cell_id": cell_id or "",
            "display": _default_plot_display("image", index),
            "viz_spec": build_report_viz_spec(
                {
                    "kind": "image",
                    "source": raw,
                    "title": title,
                    "caption": caption,
                    "display": _default_plot_display("image", index),
                    **semantic,
                }
            ).model_dump(),
            **semantic,
        }

    cleaned = _clean_base64_payload(raw)
    if cleaned.startswith("{") or cleaned.startswith("["):
        source, display = _normalize_plotly_payload(raw, index)
        semantic = infer_plot_semantics("plotly", source, title=title, caption=caption)
        return {
            "kind": "plotly",
            "mime_type": "application/vnd.plotly.v1+json",
            "source": source,
            "title": title,
            "caption": caption,
            "source_cell_id": cell_id or "",
            "display": display,
            "viz_spec": build_report_viz_spec(
                {
                    "kind": "plotly",
                    "source": source,
                    "title": title,
                    "caption": caption,
                    "display": display,
                    **semantic,
                }
            ).model_dump(),
            **semantic,
        }

    if len(cleaned) > 120 and re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
        semantic = infer_plot_semantics("image", cleaned, title=title, caption=caption)
        return {
            "kind": "image",
            "mime_type": "image/png",
            "source": f"data:image/png;base64,{cleaned}",
            "title": title,
            "caption": caption,
            "source_cell_id": cell_id or "",
            "display": _default_plot_display("image", index),
            "viz_spec": build_report_viz_spec(
                {
                    "kind": "image",
                    "source": f"data:image/png;base64,{cleaned}",
                    "title": title,
                    "caption": caption,
                    "display": _default_plot_display("image", index),
                    **semantic,
                }
            ).model_dump(),
            **semantic,
        }

    semantic = infer_plot_semantics("image", raw, title=title, caption=caption)
    return {
        "kind": "image",
        "mime_type": "image/png",
        "source": raw,
        "title": title,
        "caption": caption,
        "source_cell_id": cell_id or "",
        "display": _default_plot_display("image", index),
        "viz_spec": build_report_viz_spec(
            {
                "kind": "image",
                "source": raw,
                "title": title,
                "caption": caption,
                "display": _default_plot_display("image", index),
                **semantic,
            }
        ).model_dump(),
        **semantic,
    }


def _augment_story_plot_metadata(session_id: str, story: dict) -> dict:
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        return story

    nb_path = session_dir / "notebook.ipynb"
    cell_map: dict[str, Any] = {}
    if nb_path.exists():
        try:
            nb = nbformat.read(str(nb_path), as_version=4)
            for cell in nb.cells:
                cell_id = cell.get("id")
                if cell_id:
                    cell_map[str(cell_id)] = cell
        except Exception:
            cell_map = {}

    plot_specs_map = plot_specs_by_cell(session_dir)

    sections = story.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue

        plot_metadata: list[dict[str, Any]] = []
        plot_cell_ids = section.get("plot_cell_ids") or section.get("cell_ids") or []
        raw_plots = section.get("plots") or []

        for index, plot in enumerate(raw_plots):
            cell_id = plot_cell_ids[index] if index < len(plot_cell_ids) else None
            # Attach hidden plot specs from sidecar JSONL when not already present
            if cell_id and isinstance(plot, dict) and not plot.get("plot_spec"):
                cell_specs = plot_specs_map.get(str(cell_id), [])
                if cell_specs:
                    plot = dict(plot)
                    plot["plot_spec"] = cell_specs[0]
            plot_metadata.append(
                _normalize_plot_entry(
                    plot,
                    section=section,
                    cell_id=cell_id,
                    index=index,
                )
            )

        if not plot_metadata and plot_cell_ids:
            for index, cell_id in enumerate(plot_cell_ids):
                cell = cell_map.get(str(cell_id))
                if cell:
                    plot_metadata.extend(
                        plot_artifacts_from_outputs(
                            cell.get("outputs", []) or [],
                            title=section.get("title", ""),
                            caption=section.get("visual_caption", ""),
                            source_cell_id=str(cell_id),
                            plot_specs=plot_specs_map.get(str(cell_id), []),
                        )
                    )
                else:
                    # No notebook on disk — build artifacts directly from
                    # hidden plot specs in plot_specs.jsonl (only specs with
                    # actual Plotly data, not metadata-only stubs)
                    cell_specs = plot_specs_map.get(str(cell_id), [])
                    seen_sources = set()
                    unique_specs = []
                    for spec in cell_specs:
                        if not isinstance(spec, dict):
                            continue
                        source = spec.get("source")
                        if not source:
                            continue
                        if isinstance(source, dict) and "data" not in source:
                            continue
                        source_key = (
                            json.dumps(source, sort_keys=True, default=str)
                            if isinstance(source, dict)
                            else str(source)
                        )
                        if source_key in seen_sources:
                            continue
                        seen_sources.add(source_key)
                        unique_specs.append(spec)
                    for spec in unique_specs:
                        source = spec.get("source")
                        source_str = json.dumps(source, default=str) if isinstance(source, dict) else str(source)
                        plot_metadata.append(
                            _normalize_plot_entry(
                                {
                                    "kind": str(spec.get("kind", "plotly")).lower(),
                                    "mime_type": spec.get("mime_type", "application/vnd.plotly.v1+json"),
                                    "source": source_str,
                                    "title": spec.get("title") or section.get("title", ""),
                                    "caption": spec.get("caption") or section.get("visual_caption", ""),
                                    "source_cell_id": str(cell_id),
                                    "chart_family": spec.get("chart_family", "unknown"),
                                    "semantic_intent": spec.get("semantic_intent", "unknown"),
                                    "x_axis_role": spec.get("x_axis_role", "unknown"),
                                    "y_axis_role": spec.get("y_axis_role", "unknown"),
                                    "semantic_confidence": float(spec.get("semantic_confidence", 0.85)),
                                    "plot_spec": spec,
                                },
                                section=section,
                                cell_id=str(cell_id),
                                index=index,
                            )
                        )

        if plot_metadata:
            section["plots"] = plot_metadata

    return story


def _story_to_markdown(story: dict) -> str:
    """Convert story JSON to markdown string."""
    lines = [f"# {story.get('title', 'EDA Report')}\n"]
    summary = story.get("executive_summary", "")
    if summary:
        lines.append(f"{summary}\n")
    for section in story.get("sections", []):
        lines.append(f"## {section.get('title', section.get('phase', ''))}\n")
        lines.append(f"{section.get('content', '')}\n")

        plot_metadata = section.get("plots") or []
        if isinstance(plot_metadata, list) and plot_metadata:
            lines.append("\n**Figures:**\n")
            for plot in plot_metadata:
                if isinstance(plot, dict):
                    payload = str(plot.get("source", "")).strip()
                    caption = str(plot.get("caption") or plot.get("title") or "Figure").strip()
                    if plot.get("kind") == "image" and payload:
                        lines.append(f"![{caption}]({payload})\n")
                    elif payload:
                        lines.append(f"- {caption}\n")
                else:
                    lines.append(f"- {plot}\n")
    return "\n".join(lines)


def _story_to_pdf_lines(story: dict) -> list[tuple[str, str]]:
    """Flatten a story dict into styled text lines for the PDF fallback."""
    lines: list[tuple[str, str]] = []

    def add_heading(text: str, level: str = "h1") -> None:
        if text:
            lines.append((level, text.strip()))

    def add_paragraph(text: str) -> None:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            lines.append(("blank", ""))
            return
        for wrapped in textwrap.wrap(cleaned, width=90, break_long_words=False, break_on_hyphens=False):
            lines.append(("p", wrapped))

    add_heading(story.get("title", "EDA Report"), "h1")
    generated_at = story.get("generated_at")
    if generated_at:
        add_paragraph(f"Generated {generated_at}")

    summary = story.get("executive_summary", "")
    if summary:
        add_heading("Executive Summary", "h2")
        for paragraph in summary.split("\n"):
            add_paragraph(paragraph)

    for section in story.get("sections", []):
        title = section.get("title", section.get("phase", "Section"))
        add_heading(title, "h2")
        content = section.get("content", "")
        if content:
            for paragraph in content.split("\n"):
                add_paragraph(paragraph)

        insights = section.get("insights") or []
        if isinstance(insights, list) and insights:
            add_heading("Key Takeaways", "h3")
            for insight in insights:
                if isinstance(insight, dict):
                    desc = str(insight.get("description", "")).strip()
                    label = str(insight.get("type", "")).strip()
                    parts = [p for p in [label, desc] if p]
                    if parts:
                        add_paragraph(f"- {' - '.join(parts)}")
                else:
                    add_paragraph(f"- {insight}")

        plots = section.get("plots") or []
        if isinstance(plots, list) and plots:
            add_heading("Visuals", "h3")
            for plot in plots[:6]:
                if isinstance(plot, dict):
                    caption = str(plot.get("caption") or plot.get("title") or "Figure").strip()
                    payload = str(plot.get("source") or "").strip()
                    if plot.get("kind") == "image" and payload:
                        add_paragraph(f"- {caption}: {payload}")
                    else:
                        add_paragraph(f"- {caption}")
                else:
                    add_paragraph(f"- {plot}")

        lines.append(("blank", ""))

    return lines


def _escape_pdf_text(text: str) -> str:
    safe = unicodedata.normalize("NFKD", text).encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_minimal_pdf(story: dict) -> bytes:
    """Build a simple text PDF without third-party rendering dependencies."""
    width = 612
    height = 792
    margin_x = 54
    margin_top = 54
    line_height = 14
    bottom_margin = 54
    max_lines_per_page = max(1, (height - margin_top - bottom_margin) // line_height)

    flattened = _story_to_pdf_lines(story)
    pages: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []

    for kind, text in flattened:
        if current and len(current) >= max_lines_per_page:
            pages.append(current)
            current = []
        current.append((kind, text))
    if current:
        pages.append(current)

    def render_page(page_lines: list[tuple[str, str]]) -> bytes:
        content = io.StringIO()
        content.write("BT\n")
        y = height - margin_top
        for kind, text in page_lines:
            if kind == "blank":
                y -= line_height
                continue

            font = "/F2" if kind in {"h1", "h2", "h3"} else "/F1"
            size = "18" if kind == "h1" else "14" if kind == "h2" else "12" if kind == "h3" else "11"
            content.write(f"{font} {size} Tf\n")
            content.write(f"1 0 0 1 {margin_x} {y} Tm\n")
            content.write(f"({_escape_pdf_text(text)}) Tj\n")
            y -= line_height if kind == "p" else line_height + 4
        content.write("ET\n")
        return content.getvalue().encode("latin-1", "replace")

    object_defs: list[tuple[int, bytes]] = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b""),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        (4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"),
    ]

    next_obj = 5
    page_nums: list[int] = []
    for page_lines in pages or [[("h1", story.get("title", "EDA Report"))]]:
        content_stream = render_page(page_lines)
        content_obj_num = next_obj + 1
        page_nums.append(next_obj)
        object_defs.append(
            (
                next_obj,
                (
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
                    + str(width).encode("ascii")
                    + b" "
                    + str(height).encode("ascii")
                    + b"] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents "
                    + str(content_obj_num).encode("ascii")
                    + b" 0 R >>"
                ),
            )
        )
        object_defs.append(
            (
                content_obj_num,
                b"<< /Length "
                + str(len(content_stream)).encode("ascii")
                + b" >>\nstream\n"
                + content_stream
                + b"endstream",
            )
        )
        next_obj += 2

    object_defs[1] = (
        2,
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{num} 0 R".encode("ascii") for num in page_nums)
        + b"] /Count "
        + str(len(page_nums)).encode("ascii")
        + b" >>",
    )

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj_num, obj_bytes in sorted(object_defs, key=lambda item: item[0]):
        offsets.append(buffer.tell())
        buffer.write(f"{obj_num} 0 obj\n".encode("ascii"))
        buffer.write(obj_bytes)
        buffer.write(b"\nendobj\n")

    xref_start = buffer.tell()
    buffer.write(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    buffer.write(
        b"trailer\n<< /Size "
        + str(len(offsets)).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_start).encode("ascii")
        + b"\n%%EOF"
    )
    return buffer.getvalue()


def _story_pdf_filename(story: dict) -> str:
    """Build a safe PDF filename from the story title."""
    title = str(story.get("title", "eda-report")).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
    return f"{slug or 'eda-report'}.pdf"


def _export_story_pdf(story: dict) -> bytes:
    """Export story as PDF, using WeasyPrint when available and a local fallback otherwise."""
    md_text = _story_to_markdown(story)
    try:
        import markdown as md_lib
        import weasyprint

        html_body = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
        full_html = (
            "<html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:sans-serif;max-width:800px;margin:0 auto;padding:28px;line-height:1.5;color:#111}"
            "h1,h2,h3{line-height:1.2}"
            "img{max-width:100%}"
            "pre{background:#f5f5f5;padding:10px;overflow-x:auto}"
            "blockquote{border-left:4px solid #ddd;padding-left:12px;color:#555}"
            "</style></head><body>"
            f"{html_body}</body></html>"
        )
        return weasyprint.HTML(string=full_html).write_pdf()
    except Exception as exc:
        _LOG.warning("Story PDF render fell back to built-in PDF writer: %s", exc)
        return _build_minimal_pdf(story)


@router.get("/story/{session_id}")
async def get_story(session_id: str, format: str = Query("json")):
    """Return the story in the requested format (json, md, pdf)."""
    story = _load_story(session_id)

    story = _augment_story_plot_metadata(session_id, story)

    if format == "md":
        md = _story_to_markdown(story)
        return PlainTextResponse(md, media_type="text/markdown")

    if format == "pdf":
        pdf_bytes = _export_story_pdf(story)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{_story_pdf_filename(story)}"'},
        )

    # Default: return JSON — sanitize NaN/Inf that can't be serialized
    import math

    def _sanitize(obj):
        if isinstance(obj, float):
            return None if (math.isnan(obj) or math.isinf(obj)) else obj
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    return _sanitize(story)


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
    plot_specs_map = plot_specs_by_cell(session_dir)

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
                "plot_cell_ids": [],
                "plots": [],
                "insights": [],
            }
            sections.append(current_section)
        elif cell.cell_type == "code" and current_section is not None:
            # Attach code cell outputs as context
            cell_id = cell.get("id", "")
            current_section["cell_ids"].append(cell_id)
            # Extract text outputs for summary
            outputs = cell.get("outputs", [])
            for output in outputs:
                text = output.get("text", "")
                if not text and "data" in output:
                    text = output["data"].get("text/plain", "")
                if text:
                    current_section["content"] += f"\n\nOutput:\n{text[:300]}"

            output_artifacts = plot_artifacts_from_outputs(
                outputs,
                title=current_section.get("title", ""),
                caption=current_section.get("visual_caption", ""),
                source_cell_id=cell_id,
                plot_specs=plot_specs_map.get(cell_id, []),
            )
            if output_artifacts:
                if cell_id not in current_section["plot_cell_ids"]:
                    current_section["plot_cell_ids"].append(cell_id)
                current_section["plots"].extend(output_artifacts)

    if not sections:
        # Fallback: one section per code cell
        for i, cell in enumerate(code_cells):
            sections.append({
                "phase": f"Cell {i+1}",
                "title": f"Analysis {i+1}",
                "content": cell.source[:200],
                "cell_ids": [],
                "plot_cell_ids": [],
                "plots": [],
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
