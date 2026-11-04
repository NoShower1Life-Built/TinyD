import pytest

from packages.agent_kernel.src import AgentRuntimeKernel, ToolBlocked


def test_executes_and_persists_artifact(tmp_path):
    kernel = AgentRuntimeKernel(tmp_path / "kernel.db", seed=7)
    kernel.register_tool("echo", lambda payload: {"echo": payload["value"]})
    result = kernel.run({"value": 42}, tool_name="echo", execution_id="run-1")
    assert result["status"] == "succeeded"
    assert result["output"] == {"echo": 42}
    assert kernel.store.get_artifact("run-1")["status"] == "succeeded"
    assert kernel.store.verify_artifact_chain()


def test_hotblock_prevents_handler_invocation(tmp_path):
    kernel = AgentRuntimeKernel(tmp_path / "kernel.db")
    called = []
    kernel.register_tool("danger", lambda payload: called.append(True))
    kernel.hotblock.block("danger", "operator block")
    result = kernel.run({}, tool_name="danger", execution_id="run-blocked")
    assert result["status"] == "failed"
    assert called == []
    assert "ToolBlocked" in result["error"]


def test_bandit_updates_only_from_explicit_reward(tmp_path):
    kernel = AgentRuntimeKernel(tmp_path / "kernel.db", seed=1)
    kernel.register_tool("echo", lambda payload: {"ok": True})
    result = kernel.run({}, tool_name="echo", execution_id="run-reward")
    assert result["status"] == "succeeded"
    stats = kernel.reward("run-reward", 1.0)
    assert stats["alpha"] == 2.0
    assert stats["beta"] == 1.0
    with pytest.raises(Exception):
        kernel.reward("run-reward", 0.0)


def test_blocked_tools_are_not_selected(tmp_path):
    kernel = AgentRuntimeKernel(tmp_path / "kernel.db", seed=1)
    kernel.register_tool("blocked", lambda payload: None)
    kernel.register_tool("available", lambda payload: {"ok": True})
    kernel.hotblock.block("blocked", "test")
    assert kernel.policy.select(kernel.registry.names()) == "available"


def test_failed_tool_is_artifacted_and_chain_verifies(tmp_path):
    kernel = AgentRuntimeKernel(tmp_path / "kernel.db")
    def fail(_payload):
        raise RuntimeError("expected failure")
    kernel.register_tool("fail", fail)
    result = kernel.run({}, tool_name="fail", execution_id="run-fail")
    assert result["status"] == "failed"
    assert kernel.store.verify_artifact_chain()
