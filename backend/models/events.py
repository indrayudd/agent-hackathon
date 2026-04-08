"""Pydantic models for agent streaming events."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ThinkingEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    content: str


class CellWriteEvent(BaseModel):
    type: Literal["cell_write"] = "cell_write"
    cell_id: str
    cell_type: Literal["code", "markdown"] = "code"
    source: str
    overwrite: bool = False


class CellExecutingEvent(BaseModel):
    type: Literal["cell_executing"] = "cell_executing"
    cell_id: str


class CellOutputEvent(BaseModel):
    type: Literal["cell_output"] = "cell_output"
    cell_id: str
    outputs: list[dict[str, Any]]


class CellErrorEvent(BaseModel):
    type: Literal["cell_error"] = "cell_error"
    cell_id: str
    error: str
    traceback: list[str] = []


class CellUpdateEvent(BaseModel):
    type: Literal["cell_update"] = "cell_update"
    cell_id: str
    source: str


class CellDeleteEvent(BaseModel):
    type: Literal["cell_delete"] = "cell_delete"
    cell_id: str


class PhaseTransitionEvent(BaseModel):
    type: Literal["phase_transition"] = "phase_transition"
    phase: str
    message: str = ""


class BacktrackEvent(BaseModel):
    type: Literal["backtrack"] = "backtrack"
    reason: str


class CompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    summary: str = ""


# Union type for all events
AgentEvent = (
    ThinkingEvent
    | CellWriteEvent
    | CellExecutingEvent
    | CellOutputEvent
    | CellErrorEvent
    | CellUpdateEvent
    | CellDeleteEvent
    | PhaseTransitionEvent
    | BacktrackEvent
    | CompleteEvent
)
