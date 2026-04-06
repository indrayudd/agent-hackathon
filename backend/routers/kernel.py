"""Kernel router: placeholder for Jupyter Kernel Gateway proxy."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["kernel"])


@router.get("/kernel/{session_id}/status")
async def kernel_status(session_id: str):
    """Placeholder: return kernel status for a session.

    Full kernel WebSocket proxy will be implemented later when
    Jupyter Kernel Gateway is set up.
    """
    return {"status": "not_implemented"}
