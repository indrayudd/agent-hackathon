"""Pydantic models for story."""
from __future__ import annotations

from pydantic import BaseModel


class InsightCardModel(BaseModel):
    type: str = ""
    description: str = ""
    phase: str = ""
    rule: int = 0
    confidence: float | None = None


class StorySectionModel(BaseModel):
    phase: str
    title: str
    content: str
    plots: list[str] = []
    insights: list[InsightCardModel] = []


class StoryResponse(BaseModel):
    title: str = ""
    executive_summary: str = ""
    sections: list[StorySectionModel] = []
    generated_at: str = ""


class StoryExportRequest(BaseModel):
    format: str = "pdf"
