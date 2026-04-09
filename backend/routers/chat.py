"""Chat agent endpoints (REST + WebSocket)."""
from __future__ import annotations

import datetime
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.chat.chat_agent import build_chat_agent

_LOG = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# In-memory state cache per session (populated by pipeline run)
_session_states: dict[str, dict] = {}
_session_kgs: dict = {}

def set_session_kg(session_id: str, kg) -> None:
    """Called after pipeline completes to make KG available to chat."""
    _session_kgs[session_id] = kg


def set_session_state(session_id: str, state: dict) -> None:
    """Called after pipeline completes to make state available to chat."""
    _session_states[session_id] = state


@router.websocket("/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    """Accept a WebSocket connection and relay messages through the chat agent."""
    await websocket.accept()
    state = _session_states.get(session_id, {})
    # Load KG for chat context
    kg = _session_kgs.get(session_id)
    if kg is None:
        try:
            from backend.services.session_manager import get_session_dir
            from src.agent.knowledge_graph import KnowledgeGraph
            story_path = get_session_dir(session_id) / "story.json"
            if story_path.exists():
                story_data = json.loads(story_path.read_text())
                if "knowledge_graph" in story_data:
                    kg = KnowledgeGraph.from_dict(story_data["knowledge_graph"])
                    _session_kgs[session_id] = kg
        except Exception:
            pass
    agent = build_chat_agent(session_id, state, kg=kg)

    try:
        while True:
            data = await websocket.receive_json()
            user_msg = data.get("content", data.get("message", ""))
            _LOG.info("Chat [%s]: %s", session_id, user_msg[:100])

            response = agent(user_msg)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        _LOG.info("Chat client disconnected for session %s", session_id)


class ChatRequest(BaseModel):
    content: str
    cells: list[dict] | None = None


@router.post("/chat/{session_id}/message")
async def chat_message(session_id: str, req: ChatRequest):
    """REST endpoint for chat — handles questions, actions, and hypothesis investigations."""
    state = {**_session_states.get(session_id, {})}
    # Merge current cells from frontend so the LLM knows what exists
    if req.cells is not None:
        state["cells"] = req.cells

    # Check if this is a hypothesis request (user wants investigation, not just answer)
    try:
        from src.agent.hypothesis import hypothesis_from_user_question
        hyp = hypothesis_from_user_question(
            req.content,
            columns=state.get("columns", []),
            numeric_cols=state.get("numeric_cols", []),
            time_col=state.get("time_col"),
        )
        if hyp is not None:
            return _run_hypothesis_investigation(session_id, state, hyp, req.content)
    except Exception as exc:
        _LOG.warning("Hypothesis detection failed: %s", exc)

    # Load KG for chat context
    kg = _session_kgs.get(session_id)
    if kg is None:
        try:
            from backend.services.session_manager import get_session_dir
            from src.agent.knowledge_graph import KnowledgeGraph
            story_path = get_session_dir(session_id) / "story.json"
            if story_path.exists():
                story_data = json.loads(story_path.read_text())
                if "knowledge_graph" in story_data:
                    kg = KnowledgeGraph.from_dict(story_data["knowledge_graph"])
                    _session_kgs[session_id] = kg
        except Exception:
            pass

    # Normal chat flow
    agent = build_chat_agent(session_id, state, kg=kg)
    response = agent(req.content)
    _LOG.info("Chat REST [%s]: %s -> %s", session_id, req.content[:60], response.get("content", "")[:60])

    # Handle structured actions
    action_type = response.get("action_type")
    if action_type:
        try:
            from backend.services.kernel_manager import execute_code, is_kernel_alive
            from backend.services.session_manager import get_session_dir
            from backend.routers.stream import push_event

            _ensure_kernel(session_id)

            if action_type == "new_cell":
                response = _handle_new_cell(session_id, response, req.content, push_event, execute_code)

            elif action_type == "edit_cell":
                response = _handle_edit_cell(session_id, response, req.content, push_event, execute_code)

            elif action_type == "delete_cells":
                response = _handle_delete_cells(session_id, response, req.content, push_event)

            elif action_type == "reorder_cell":
                response = _handle_reorder_cell(session_id, response, req.content, push_event)

        except Exception as exc:
            _LOG.warning("Chat action failed: %s", exc)
            response["content"] += f"\n\nCouldn't execute action: {exc}"

    return response


def _ensure_kernel(session_id: str):
    """Make sure the kernel is alive and has data loaded."""
    from backend.services.kernel_manager import execute_code, is_kernel_alive
    from backend.services.session_manager import get_session_dir

    if not is_kernel_alive(session_id):
        session_dir = get_session_dir(session_id)
        uploads = list((session_dir / "uploads").iterdir())
        if uploads:
            dataset_path = str(uploads[0])
            load_code = f'import pandas as pd\nimport numpy as np\nimport matplotlib\nmatplotlib.use("Agg")\nimport matplotlib.pyplot as plt\ndf = pd.read_csv("{dataset_path}")\nprint(f"Reloaded {{len(df)}} rows")'
            execute_code(session_id, load_code, timeout=15)


def _execute_and_push(session_id: str, cell_id: str, code: str, push_event, execute_code) -> tuple[list, str | None]:
    """Execute code in kernel and push output/error events. Returns (outputs, error)."""
    push_event(session_id, {"type": "cell_executing", "cell_id": cell_id})
    outputs, error = execute_code(session_id, code, timeout=30)

    if error:
        push_event(session_id, {"type": "cell_error", "cell_id": cell_id, "error": error})
    else:
        push_event(session_id, {"type": "cell_output", "cell_id": cell_id, "outputs": outputs})

    return outputs, error


def _handle_new_cell(session_id, response, user_msg, push_event, execute_code):
    """Create a new cell, execute it, push events."""
    code = response["action_code"]
    cell_id = f"chat_cell_{int(time.time())}"

    push_event(session_id, {
        "type": "cell_write",
        "cell_id": cell_id,
        "cell_type": "code",
        "source": code,
    })

    # Log user action in activity
    push_event(session_id, {
        "type": "chat_action",
        "action": "new_cell",
        "detail": f"New cell: {user_msg[:60]}",
        "cell_id": cell_id,
    })

    outputs, error = _execute_and_push(session_id, cell_id, code, push_event, execute_code)
    response = _append_output_summary(response, outputs, error)
    _snapshot(session_id, f"Chat: {user_msg[:40]}")
    return response


def _handle_edit_cell(session_id, response, user_msg, push_event, execute_code):
    """Edit an existing cell's source and re-execute."""
    cell_id = response["target_cell_id"]
    code = response["action_code"]

    # Push source update
    push_event(session_id, {
        "type": "cell_update",
        "cell_id": cell_id,
        "source": code,
    })

    # Log user action in activity
    push_event(session_id, {
        "type": "chat_action",
        "action": "edit_cell",
        "detail": f"Edited: {user_msg[:60]}",
        "cell_id": cell_id,
    })

    outputs, error = _execute_and_push(session_id, cell_id, code, push_event, execute_code)
    response = _append_output_summary(response, outputs, error)
    _snapshot(session_id, f"Edit: {user_msg[:40]}")
    return response


def _handle_delete_cells(session_id, response, user_msg, push_event):
    """Delete one or more cells."""
    cell_ids = response.get("target_cell_ids", [])
    for cid in cell_ids:
        push_event(session_id, {"type": "cell_delete", "cell_id": cid})

    push_event(session_id, {
        "type": "chat_action",
        "action": "delete_cells",
        "detail": f"Deleted {len(cell_ids)} cell(s): {user_msg[:60]}",
        "cell_ids": cell_ids,
    })

    _snapshot(session_id, f"Delete: {user_msg[:40]}")
    return response


def _handle_reorder_cell(session_id, response, user_msg, push_event):
    """Move a cell up or down."""
    cell_id = response["target_cell_id"]
    direction = response["direction"]

    push_event(session_id, {
        "type": "cell_reorder",
        "cell_id": cell_id,
        "direction": direction,
    })

    push_event(session_id, {
        "type": "chat_action",
        "action": "reorder_cell",
        "detail": f"Moved {direction}: {user_msg[:60]}",
        "cell_id": cell_id,
    })

    _snapshot(session_id, f"Reorder: {user_msg[:40]}")
    return response


def _append_output_summary(response: dict, outputs: list, error: str | None) -> dict:
    """Append execution result summary to the response content."""
    if error:
        response["content"] += f"\n\nError executing code: {error}"
    else:
        output_text = "\n".join(o.get("text", "") for o in outputs if o.get("text"))
        if output_text:
            response["content"] += f"\n\nResult:\n{output_text[:500]}"
        else:
            response["content"] += "\n\nCode executed — check the notebook for the output."
    return response


def _snapshot(session_id: str, label: str):
    """Create a version snapshot, swallowing errors."""
    try:
        from src.reporting.versioning import create_snapshot
        create_snapshot(session_id, label)
    except Exception as exc:
        _LOG.warning("Snapshot failed: %s", exc)


def _run_hypothesis_investigation(session_id: str, state: dict, hyp, user_question: str) -> dict:
    """Run a full subagent investigation for a user hypothesis."""
    from backend.services.kernel_manager import execute_code, is_kernel_alive
    from backend.services.session_manager import get_session_dir
    from backend.routers.stream import push_event
    from src.agent.subagent import run_subagent

    # Check KG for existing answer
    kg = _session_kgs.get(session_id)
    if kg is None:
        # Try to load KG from story.json
        try:
            from backend.services.session_manager import get_session_dir
            from src.agent.knowledge_graph import KnowledgeGraph
            story_path = get_session_dir(session_id) / "story.json"
            if story_path.exists():
                story_data = json.loads(story_path.read_text())
                if "knowledge_graph" in story_data:
                    kg = KnowledgeGraph.from_dict(story_data["knowledge_graph"])
                    _session_kgs[session_id] = kg
                    _LOG.info("Loaded KG from story.json for session %s", session_id)
        except Exception as exc:
            _LOG.warning("Failed to load KG from story.json: %s", exc)
    if kg is not None:
        existing = kg.find_similar_hypothesis(hyp, threshold=0.5)
        if existing and existing.confidence > 0.6:
            return {
                "role": "agent",
                "type": "text",
                "content": (
                    f"**Previously investigated:** {existing.phase.replace('Investigation: ', '')}\n\n"
                    f"{existing.text}\n\n"
                    f"*Confidence: {existing.confidence:.0%}* (from earlier investigation)"
                ),
                "action_code": None,
            }

    _LOG.info("Running hypothesis investigation for session %s: %s", session_id, hyp.title)

    # Create a dedicated notebook for this chat investigation
    chat_notebook_id = f"chat_{int(time.time())}"

    push_event(session_id, {
        "type": "subagent_start",
        "hypothesis_id": hyp.id,
        "notebook_id": chat_notebook_id,
        "title": hyp.title,
    })

    # Note: don't auto-switch to chat notebook tab — let the user choose to view it.
    # The tab will appear in the sidebar/tab bar via the subagent_start event.

    # Ensure kernel has data
    if not is_kernel_alive(session_id):
        session_dir = get_session_dir(session_id)
        uploads = list((session_dir / "uploads").iterdir())
        if uploads:
            load_code = f'import pandas as pd\nimport numpy as np\nimport matplotlib.pyplot as plt\n%matplotlib inline\ndf = pd.read_csv("{uploads[0]}")\nprint(f"Loaded {{len(df)}} rows")'
            execute_code(session_id, load_code, timeout=15)

    # Push investigation start
    push_event(session_id, {"type": "phase_transition", "phase": f"Chat Investigation: {hyp.title}", "notebook_id": chat_notebook_id})
    push_event(session_id, {"type": "cell_write", "cell_id": f"chat_hyp_header", "cell_type": "markdown", "source": f"### Chat Investigation: {hyp.title}\n\n{hyp.description}", "notebook_id": chat_notebook_id})

    # Get current cell count from notebook
    cell_counter = [int(time.time()) % 10000]

    try:
        result = run_subagent(
            hypothesis_id=hyp.id,
            hypothesis_title=hyp.title,
            hypothesis_description=hyp.description,
            relevant_cols=hyp.relevant_cols,
            all_columns=state.get("columns", []),
            time_col=state.get("time_col"),
            session_id=session_id,
            push_event=push_event,
            execute_code=execute_code,
            cell_counter=cell_counter,
            max_cells=5,
            notebook_id=chat_notebook_id,
        )

        # Write conclusion cell to the chat notebook
        conf_pct = int(result.confidence * 100)
        conf_label = "High" if conf_pct >= 70 else "Medium" if conf_pct >= 40 else "Low"
        push_event(session_id, {
            "type": "cell_write",
            "cell_id": f"{chat_notebook_id}_conclusion",
            "cell_type": "markdown",
            "source": f"### Conclusion\n\n{result.finding}\n\n**Confidence:** {conf_label} ({conf_pct}%)",
            "notebook_id": chat_notebook_id,
        })

        # Update story with new investigation
        try:
            session_dir = get_session_dir(session_id)
            story_path = session_dir / "story.json"
            if story_path.exists():
                story = json.loads(story_path.read_text())
                story.setdefault("sections", []).append({
                    "phase": f"Investigation: {hyp.title}",
                    "title": hyp.title,
                    "content": result.finding,
                    "cell_ids": result.cell_ids,
                    "type": "investigation",
                    "confidence": result.confidence,
                })
                story["generated_at"] = datetime.datetime.now().isoformat()
                story_path.write_text(json.dumps(story, default=str, indent=2))

            from src.reporting.versioning import create_snapshot
            create_snapshot(session_id, f"Investigation: {hyp.title[:40]}")
        except Exception as exc:
            _LOG.warning("Story update/snapshot failed for investigation %s: %s", hyp.title, exc)

        push_event(session_id, {
            "type": "subagent_complete",
            "hypothesis_id": hyp.id,
            "notebook_id": chat_notebook_id,
            "finding": result.finding,
            "confidence": result.confidence,
        })

        return {
            "role": "agent",
            "type": "text",
            "content": f"**Investigation: {hyp.title}**\n\n{result.finding}\n\n*Confidence: {result.confidence:.0%}*",
            "action_code": None,
        }

    except Exception as exc:
        _LOG.warning("Hypothesis investigation failed: %s", exc)
        push_event(session_id, {
            "type": "subagent_complete",
            "hypothesis_id": getattr(hyp, 'id', 'unknown'),
            "notebook_id": chat_notebook_id,
            "finding": f"Investigation failed: {exc}",
            "confidence": 0.0,
        })
        return {
            "role": "agent",
            "type": "text",
            "content": f"I tried to investigate '{hyp.title}' but encountered an error: {exc}",
            "action_code": None,
        }
