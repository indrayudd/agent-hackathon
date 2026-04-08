"""Pydantic models for story."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlotDisplayModel(BaseModel):
    width: int = 960
    height: int = 540
    aspect_ratio: float = 960 / 540
    fit: Literal["contain", "cover"] = "contain"
    native_width: int | None = None
    native_height: int | None = None
    max_width: int = 960
    max_height: int = 540


class PlotVizChannelModel(BaseModel):
    axis: Literal["x", "y"]
    role: Literal["time", "category", "ordinal", "numeric", "index", "measure", "count", "density", "unknown"] = "unknown"
    scale: Literal["linear", "band", "time", "ordinal", "log", "unknown"] = "unknown"
    label: str = ""


class PlotLegendModel(BaseModel):
    show: bool = False
    position: Literal["top", "right", "bottom", "none"] = "none"


class PlotVizSpecModel(BaseModel):
    renderer: Literal["report_d3", "plotly", "image", "unknown"] = "unknown"
    fallback_renderer: Literal["report_d3", "plotly", "image", "unknown"] = "unknown"
    chart_family: Literal["scatter", "line", "bar", "histogram", "box", "violin", "heatmap", "image", "unknown"] = "unknown"
    semantic_intent: Literal["trend", "comparison", "distribution", "relationship", "matrix", "residual", "unknown"] = "unknown"
    mark: Literal["point", "line", "bar", "rect", "box", "violin", "heatmap", "image", "unknown"] = "unknown"
    orientation: Literal["vertical", "horizontal", "matrix", "none"] = "none"
    trace_count: int = 0
    report_native: bool = False
    x: PlotVizChannelModel = Field(default_factory=lambda: PlotVizChannelModel(axis="x"))
    y: PlotVizChannelModel = Field(default_factory=lambda: PlotVizChannelModel(axis="y"))
    legend: PlotLegendModel = Field(default_factory=PlotLegendModel)
    interactions: list[Literal["hover", "focus", "zoom", "pan", "source_link"]] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    display: PlotDisplayModel = Field(default_factory=PlotDisplayModel)


class PlotArtifactModel(BaseModel):
    kind: Literal["image", "plotly"]
    mime_type: str
    source: str
    title: str = ""
    caption: str = ""
    source_path: str | None = None
    source_cell_id: str | None = None
    display: PlotDisplayModel = Field(default_factory=PlotDisplayModel)
    chart_family: Literal["scatter", "line", "bar", "histogram", "box", "violin", "heatmap", "image", "unknown"] = "unknown"
    semantic_intent: Literal["trend", "comparison", "distribution", "relationship", "matrix", "residual", "unknown"] = "unknown"
    x_axis_role: Literal["time", "category", "ordinal", "numeric", "index", "measure", "count", "density", "unknown"] = "unknown"
    y_axis_role: Literal["time", "category", "ordinal", "numeric", "index", "measure", "count", "density", "unknown"] = "unknown"
    semantic_confidence: float = 0.0
    plot_spec: dict[str, Any] | None = None
    viz_spec: PlotVizSpecModel = Field(default_factory=PlotVizSpecModel)


class InsightCardModel(BaseModel):
    type: str = ""
    description: str = ""
    phase: str = ""
    rule: int = 0
    confidence: float | None = None


class StorySectionModel(BaseModel):
    phase: str = ""
    title: str = ""
    content: str = ""
    summary: str = ""
    subtitle: str = ""
    plots: list[PlotArtifactModel] = Field(default_factory=list)
    insights: list[InsightCardModel] = Field(default_factory=list)
    cell_ids: list[str] = Field(default_factory=list)
    plot_cell_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    visual_title: str = ""
    visual_caption: str = ""


class StoryResponse(BaseModel):
    title: str = ""
    executive_summary: str = ""
    sections: list[StorySectionModel] = Field(default_factory=list)
    generated_at: str = ""


class StoryExportRequest(BaseModel):
    format: str = "pdf"
