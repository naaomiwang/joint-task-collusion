"""Verbatim communication mode. No model calls."""

import glob
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import experiments.episode_runner as er
from experiments.models import AgentRuntime, EpisodeRunConfig
from experiments.prompts.system import initial_agent_messages
from experiments.protocol.messaging import _format_private_raw_log
from experiments.protocol.state import agent_state, create_channel_state, reset_message_delivery
from experiments.protocol.verbatim import (
    EXCERPT_DELIMITER, VERBATIM_ATTEMPTS, _send_verbatim, is_verbatim, log_views,
)

REPO = Path(__file__).resolve().parents[1]


def _state():
    state = create_channel_state("ep", comm_mode="verbatim")
    for a in ("alice", "bob"):
        agent_state(state, a)["private_raw_log"] = [
            {"seq": 1, "tool": "run_tests", "arguments": {},
             "result": {"success": True, "toolchain_output": "FAILED test_x - assert 6 == 4\n   where 6 = f('IV')"}},
            {"seq": 2, "tool": "save_final_answer", "arguments": {"reasoning": "The docstring says \"IV\" is 4.", "answer": "bug"},
             "result": {"success": True}}]
    return state


def test_matching_rules():
    views = log_views(_format_private_raw_log(agent_state(_state(), "alice")))
    assert is_verbatim('"answer":"bug"', views)                      # serialized form
    assert is_verbatim("assert 6 == 4  where 6 = f('IV')", views)     # escapes decoded, whitespace collapsed
    assert is_verbatim('The docstring says "IV" is 4.', views)
    assert not is_verbatim("assert 6 == 5", views)                    # edited
    assert not is_verbatim("assert 6 == 4 ... is 4.", views)          # ellipsis joining passages
    assert not is_verbatim("   ", views)


def test_send_rejects_logs_and_delivers():
    state = _state()
    bad = _send_verbatim(state, "alice", {"excerpts": ['"answer":"bug"', "made up"]})
    assert not bad["success"] and "excerpt 2" in bad["error"]
    assert state["events"][-1]["verbatim_rejection"] and not agent_state(state, "alice")["delivered"]
    assert not _send_verbatim(state, "alice", {"content": "hi"})["success"]           # wrong argument
    assert not _send_verbatim(state, "alice", {"excerpts": ['"answer":"bug"'] * 20})["success"]  # over 200 chars
    ok = _send_verbatim(state, "alice", {"excerpts": ['"answer":"bug"', "assert 6 == 4"]})
    assert ok["success"]
    msg = agent_state(state, "bob")["inbox"][-1]
    assert msg["message_type"] == "raw_log_excerpt" and msg["content"] == '"answer":"bug"' + EXCERPT_DELIMITER + "assert 6 == 4"
    assert sum(1 for e in state["events"] if e.get("verbatim_rejection")) == 3


def _run(monkeypatch, fails_before_success):
    calls = Counter()

    def fake_turn(*, runtime, state, **kw):
        calls[runtime.agent_id] += 1
        n = calls[runtime.agent_id]
        excerpt = "not in the log" if n <= fails_before_success else '"answer":"bug"'
        return {"tool_calls": [{"name": "send_message", "result": _send_verbatim(state, runtime.agent_id, {"excerpts": [excerpt]})}]}

    monkeypatch.setattr(er, "_run_agent_turn_with_context_pruning", fake_turn)
    monkeypatch.setattr(er, "_phase_completed", lambda turn, phase: any(c["result"].get("success") for c in turn["tool_calls"]))
    monkeypatch.setattr(er, "_spent_an_attempt", lambda turn, phase: True)
    state = _state()
    prepared = SimpleNamespace(task_type="code_analysis", state=state,
                               agents={a: SimpleNamespace(judging_prompt=f"brief {a}") for a in ("alice", "bob")})
    runtimes = {a: AgentRuntime(agent_id=a, config=None, messages=[]) for a in ("alice", "bob")}
    config = EpisodeRunConfig(comm_mode="verbatim", max_rounds=1, verbose=False)
    er._run_communication_phase(prepared=prepared, state=state, runtimes=runtimes, episode_id="ep",
                                config=config, reasoning_traces=[], usage_records=[])
    return state, runtimes, calls


def test_two_retries_then_delivery(monkeypatch):
    state, runtimes, calls = _run(monkeypatch, fails_before_success=2)
    assert calls["alice"] == VERBATIM_ATTEMPTS == 3
    assert sum(1 for e in state["events"] if e["tool"] == "send_message" and e["success"]) == 2
    text = "\n".join(m["content"] for m in runtimes["bob"].messages if "content" in m)
    assert "[from=alice][type=raw_log_excerpt]" in text
    assert "split into" not in text and "chunk 1:" not in text


def test_round_skipped_after_three_rejections(monkeypatch):
    state, runtimes, calls = _run(monkeypatch, fails_before_success=99)
    assert calls["alice"] == 3
    assert not [e for e in state["events"] if e["tool"] == "send_message" and e["success"]]
    assert sum(1 for e in state["events"] if e.get("verbatim_rejection")) == 6


def test_system_prompt_identical_across_free_text_and_verbatim():
    paths = glob.glob(str(REPO / "results/l/f/**/run.json"), recursive=True)
    free = initial_agent_messages(agent_id="alice", max_rounds=5, reward_objective=True)[0]["content"]
    verb = initial_agent_messages(agent_id="alice", max_rounds=5, reward_objective=True, comm_mode="verbatim")[0]["content"]
    if paths:
        stored = json.load(open(paths[0], encoding="utf-8"))["run_config"]["prompt_texts"]["system_prompts"]["alice"]
        assert free == stored
    assert verb == free and "retried at most 2 times" in free
