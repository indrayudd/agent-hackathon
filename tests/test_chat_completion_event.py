"""Test that chat hypothesis investigation pushes a completion event."""
import unittest
from unittest.mock import patch, MagicMock


class TestChatCompletionEvent(unittest.TestCase):
    @patch("backend.services.kernel_manager.is_kernel_alive", return_value=True)
    @patch("backend.services.kernel_manager.execute_code")
    @patch("backend.routers.stream.push_event")
    @patch("src.agent.subagent.run_subagent")
    def test_investigation_pushes_completion_event(self, mock_subagent, mock_push, mock_exec, mock_alive):
        from src.agent.subagent import InvestigationResult
        mock_subagent.return_value = InvestigationResult(
            hypothesis_id="h1", hypothesis_title="Test", finding="Found something", confidence=0.8,
        )
        from src.agent.hypothesis import Hypothesis
        hyp = Hypothesis(id="h1", title="Test", description="Test", priority=1)
        from backend.routers.chat import _run_hypothesis_investigation
        state = {"columns": ["a", "b"], "numeric_cols": ["a"], "time_col": None}
        result = _run_hypothesis_investigation("test_session", state, hyp, "test question")
        pushed_events = [c[0][1] for c in mock_push.call_args_list]
        completion_events = [e for e in pushed_events if "complete" in e.get("type", "")]
        assert len(completion_events) >= 1, f"Expected completion event, got: {[e['type'] for e in pushed_events]}"

if __name__ == "__main__":
    unittest.main()
