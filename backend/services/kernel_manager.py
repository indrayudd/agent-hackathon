"""Real IPython kernel manager for executing code cells."""
from __future__ import annotations

import logging
import pathlib
import queue
from typing import Any

import jupyter_client

_LOG = logging.getLogger(__name__)

# Active kernels per session
_kernels: dict[str, jupyter_client.KernelManager] = {}
_clients: dict[str, jupyter_client.KernelClient] = {}

SESSIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "sessions"


def get_or_create_kernel(session_id: str) -> jupyter_client.KernelClient:
    """Get or create a kernel for a session."""
    if session_id in _clients:
        client = _clients[session_id]
        if client.is_alive():
            return client
        # Dead client, clean up
        shutdown_kernel(session_id)

    km = jupyter_client.KernelManager(kernel_name="python3")

    # Set working directory to session uploads
    session_dir = SESSIONS_DIR / session_id
    uploads_dir = session_dir / "uploads"
    cwd = str(uploads_dir if uploads_dir.exists() else session_dir)
    km.start_kernel(cwd=cwd)

    client = km.client()
    client.start_channels()
    client.wait_for_ready(timeout=30)

    _kernels[session_id] = km
    _clients[session_id] = client

    # Pre-inject common imports + inline plotting
    _execute_silent(client, """%matplotlib inline
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')
pd.set_option('display.max_columns', 50)
pd.set_option('display.max_rows', 20)
pd.set_option('display.width', 120)
""")

    _LOG.info("Kernel started for session %s (cwd=%s)", session_id, cwd)
    return client


def _execute_silent(client: jupyter_client.KernelClient, code: str, timeout: int = 30):
    """Execute code without collecting output (for setup)."""
    msg_id = client.execute(code, silent=True)
    # Wait for completion
    while True:
        try:
            msg = client.get_iopub_msg(timeout=timeout)
            if msg["parent_header"].get("msg_id") == msg_id and msg["msg_type"] == "status":
                if msg["content"]["execution_state"] == "idle":
                    break
        except queue.Empty:
            break


def execute_code(session_id: str, code: str, timeout: int = 60) -> tuple[list[dict[str, Any]], str | None]:
    """
    Execute code in the session's kernel and return structured outputs.

    Returns: (outputs, error)
        outputs: list of output dicts with output_type, text, data, etc.
        error: error string if execution failed, None otherwise
    """
    client = get_or_create_kernel(session_id)
    msg_id = client.execute(code)

    outputs: list[dict[str, Any]] = []
    error: str | None = None

    while True:
        try:
            msg = client.get_iopub_msg(timeout=timeout)
        except queue.Empty:
            error = f"Execution timed out after {timeout}s"
            break

        # Only process messages from our execution
        if msg["parent_header"].get("msg_id") != msg_id:
            continue

        msg_type = msg["msg_type"]
        content = msg["content"]

        if msg_type == "stream":
            outputs.append({
                "output_type": "stream",
                "name": content.get("name", "stdout"),
                "text": content.get("text", ""),
            })

        elif msg_type in ("execute_result", "display_data"):
            data = content.get("data", {})
            # Convert list values to strings
            clean_data = {}
            for k, v in data.items():
                clean_data[k] = v if isinstance(v, str) else "".join(v) if isinstance(v, list) else str(v)
            outputs.append({
                "output_type": msg_type,
                "data": clean_data,
                "metadata": content.get("metadata", {}),
            })

        elif msg_type == "error":
            tb = content.get("traceback", [])
            error = f"{content.get('ename', 'Error')}: {content.get('evalue', '')}"
            outputs.append({
                "output_type": "error",
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": tb,
            })

        elif msg_type == "status":
            if content["execution_state"] == "idle":
                break

    return outputs, error


def shutdown_kernel(session_id: str):
    """Shut down the kernel for a session."""
    client = _clients.pop(session_id, None)
    km = _kernels.pop(session_id, None)

    if client:
        try:
            client.stop_channels()
        except Exception:
            pass

    if km:
        try:
            km.shutdown_kernel(now=True)
        except Exception:
            pass

    _LOG.info("Kernel shut down for session %s", session_id)


def is_kernel_alive(session_id: str) -> bool:
    """Check if a session has an active kernel."""
    km = _kernels.get(session_id)
    return km is not None and km.is_alive()
