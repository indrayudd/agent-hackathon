"""Smoke tests for the multi-loop orchestrator architecture."""
import inspect
import unittest


class TestRunAgentSignature(unittest.TestCase):
    def test_accepts_new_params(self):
        from src.agent.eda_agent import run_agent
        sig = inspect.signature(run_agent)
        assert "max_subagents" in sig.parameters
        assert "max_loops" in sig.parameters
        assert "loop_timeout" in sig.parameters
        assert sig.parameters["max_subagents"].default == 3
        assert sig.parameters["max_loops"].default == 2
        assert sig.parameters["loop_timeout"].default == 180


class TestAgentStateFields(unittest.TestCase):
    def test_has_loop_fields(self):
        from src.agent.state import AgentState
        state = AgentState(dataset_path="/tmp/test.csv", session_id="test")
        assert hasattr(state, "loop_count")
        assert hasattr(state, "subagent_run_count")
        assert hasattr(state, "max_subagents")
        assert hasattr(state, "max_loops")
        assert state.loop_count == 0
        assert state.max_subagents == 3


class TestSubagentSignature(unittest.TestCase):
    def test_accepts_kernel_id(self):
        from src.agent.subagent import run_subagent
        sig = inspect.signature(run_subagent)
        assert "kernel_id" in sig.parameters
        assert "notebook_id" in sig.parameters

    def test_investigation_result_has_images(self):
        from src.agent.subagent import InvestigationResult
        result = InvestigationResult(hypothesis_id="h1", hypothesis_title="T", finding="F")
        assert hasattr(result, "images")
        assert isinstance(result.images, dict)


class TestKGIntegration(unittest.TestCase):
    def test_kg_used_in_eda_agent(self):
        with open("src/agent/eda_agent.py") as f:
            source = f.read()
        assert "KnowledgeGraph" in source
        assert "get_context_for_hypothesis_generation" in source
        assert "find_similar_hypothesis" in source
        assert "KernelPoolManager" in source
        assert "loop_start" in source
        assert "subagent_start" in source

    def test_hypothesis_accepts_kg_context(self):
        from src.agent.hypothesis import generate_hypotheses
        sig = inspect.signature(generate_hypotheses)
        assert "kg_context" in sig.parameters


class TestKernelPool(unittest.TestCase):
    def test_pool_importable(self):
        from backend.services.kernel_pool import KernelPoolManager
        pool = KernelPoolManager()
        assert hasattr(pool, "allocate_subagent_kernels")
        assert hasattr(pool, "shutdown_subagent_kernels")
        assert hasattr(pool, "inject_dataset_preamble")


class TestRunEndpointConfig(unittest.TestCase):
    def test_accepts_config_body(self):
        with open("backend/routers/run.py") as f:
            source = f.read()
        assert "RunConfig" in source
        assert "max_subagents" in source
        assert "max_loops" in source


class TestChatKGIntegration(unittest.TestCase):
    def test_chat_has_kg_support(self):
        with open("backend/routers/chat.py") as f:
            source = f.read()
        assert "set_session_kg" in source
        assert "_session_kgs" in source
        assert "find_similar_hypothesis" in source
        assert "subagent_complete" in source

    def test_chat_context_accepts_kg(self):
        from src.chat.chat_agent import ChatContext
        sig = inspect.signature(ChatContext.__init__)
        assert "kg" in sig.parameters


class TestVisionLoop(unittest.TestCase):
    def test_interpret_output_uses_content_parts(self):
        with open("src/agent/reasoning.py") as f:
            source = f.read()
        # The fix: HumanMessage(content=content_parts) instead of plain string
        assert "HumanMessage(content=content_parts)" in source


if __name__ == "__main__":
    unittest.main()
