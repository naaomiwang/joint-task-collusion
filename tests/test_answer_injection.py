"""Follow-up manipulation: answer-chunk injection in free text. No model calls."""

import glob
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

import experiments.episode_runner as er
from experiments.answer_injection import (
    CONDITIONS, answer_chunk, answer_value_span, assign_condition, inject_answer_chunks,
)
from experiments.models import AgentRuntime, EpisodeRunConfig
from experiments.protocol.messaging import _format_private_raw_log, _send_message, raw_log_chunks
from experiments.protocol.state import agent_state, create_channel_state

REPO = Path(__file__).resolve().parents[1]


def _log(answer):
    return [
        {"seq": 1, "tool": "query_database", "arguments": {"sql": "SELECT id " + "x" * 450},
         "result": {"success": True, "rows": [{"id": f"R{i:03d}"} for i in range(30)]}},
        {"seq": 2, "tool": "save_final_answer",
         "arguments": {"reasoning": 'He said "answer": no', "answer": answer}, "result": {"success": True}},
    ]


def _state(alice_answer, bob_answer):
    state = create_channel_state("ep", comm_mode="free-text")
    agent_state(state, "alice")["private_raw_log"] = _log(alice_answer)
    agent_state(state, "bob")["private_raw_log"] = _log(bob_answer)
    return state


def test_span_is_the_serialized_answer_value():
    state = _state("bug", [{"id": "R001"}, {"id": "R002"}])
    for agent in ("alice", "bob"):
        steps = agent_state(state, agent)["private_raw_log"]
        start, end = answer_value_span(steps)
        text = _format_private_raw_log(agent_state(state, agent))
        assert text[start:end] == json.dumps(steps[1]["arguments"]["answer"], ensure_ascii=False, separators=(",", ":"))


def test_chunk_uses_messaging_slicing_and_flags_a_split_value():
    state = _state("bug", [{"id": f"R{i:03d}"} for i in range(40)])  # Bob's value spans chunks
    a, b = answer_chunk(state, "alice"), answer_chunk(state, "bob")
    assert a["content"] == raw_log_chunks(state, "alice")[a["chunk_id"] - 1]
    assert a["contains_full_answer"] and not a["fallback_first_partial_chunk"]
    assert not b["contains_full_answer"] and b["fallback_first_partial_chunk"] and b["chunks_spanned"] > 1
    assert b["answer_start"] // 200 == b["chunk_id"] - 1  # first chunk that contains part of it


def test_no_answer_means_no_delivery():
    state = _state("bug", "bug")
    agent_state(state, "bob")["private_raw_log"] = _log("bug")[:1]
    record = inject_answer_chunks(state, {"alice": "V", "bob": "none"})
    assert record["alice"]["delivered"] is False and agent_state(state, "alice")["inbox"] == []


@pytest.mark.parametrize("condition,label", [("V", "raw_log_chunk"), ("E", "evidence")])
def test_labels_and_notices(condition, label):
    state = _state("bug", "no_bug")
    inject_answer_chunks(state, {"alice": condition, "bob": "none"})
    inbox = agent_state(state, "alice")["inbox"]
    assert inbox[0]["from"] == "bob" and inbox[0]["message_type"] == label
    notice = inbox[1]["content"]
    assert inbox[1]["from"] == "runner"
    if condition == "V":
        assert "verbatim" in notice and "raw log" in notice
    else:
        assert "verbatim" not in notice and "raw log" not in notice and "raw_log" not in notice
    assert agent_state(state, "bob")["inbox"][0]["from"] == "runner"  # the sender is told
    assert not [e for e in state["events"] if e["tool"] == "send_message"]


def test_injection_does_not_use_the_message_budget(monkeypatch):
    def fake_attempts(*, runtime, state, round_index, **kw):
        from experiments.protocol.state import reset_message_delivery
        reset_message_delivery(state, runtime.agent_id)
        return _send_message(state, runtime.agent_id, f"{runtime.agent_id} r{round_index + 1}", "evidence")["success"]

    monkeypatch.setattr(er, "_run_agent_attempts", fake_attempts)
    state = _state("bug", "no_bug")
    prepared = SimpleNamespace(task_type="code_analysis", state=state,
                               agents={a: SimpleNamespace(judging_prompt=f"brief {a}") for a in ("alice", "bob")})
    runtimes = {a: AgentRuntime(agent_id=a, config=None, messages=[]) for a in ("alice", "bob")}
    config = EpisodeRunConfig(comm_mode="free-text", max_rounds=5, verbose=False,
                              answer_injection={"alice": "V", "bob": "E"})
    er._run_communication_phase(prepared=prepared, state=state, runtimes=runtimes, episode_id="ep",
                                config=config, reasoning_traces=[], usage_records=[])
    sends = [e for e in state["events"] if e["tool"] == "send_message" and e["success"]]
    assert Counter(e["actor"] for e in sends) == {"alice": 5, "bob": 5}
    alice_text = "\n".join(m["content"] for m in runtimes["alice"].messages if "content" in m)
    assert "[round=1/5][from=bob][type=raw_log_chunk]" in alice_text
    bob_text = "\n".join(m["content"] for m in runtimes["bob"].messages if "content" in m)
    assert "[round=1/5][from=alice][type=evidence]" in bob_text
    assert {e["tool"] for e in state["events"]} == {"send_message", "answer_injection"}


def test_assignment_is_deterministic_and_balanced():
    draws = [assign_condition(7, f"rep{s:03d}", e, j) for s in range(1, 26) for e in range(10) for j in ("alice", "bob")]
    assert draws == [assign_condition(7, f"rep{s:03d}", e, j) for s in range(1, 26) for e in range(10) for j in ("alice", "bob")]
    counts = Counter(draws)
    assert set(counts) == set(CONDITIONS) and min(counts.values()) > 120  # of 500


def test_span_matches_every_stored_log():
    paths = glob.glob(str(REPO / "results" / "l" / "f" / "**" / "run.json"), recursive=True)
    if not paths:
        pytest.skip("no stored runs")
    checked = 0
    for p in paths:
        for e in json.load(open(p, encoding="utf-8"))["results"]:
            for a in ("alice", "bob"):
                state = create_channel_state("ep", comm_mode="free-text")
                agent_state(state, a)["private_raw_log"] = e["agents"][a]["private_raw_log"]
                pick = answer_chunk(state, a)  # raises if a located span is wrong
                checked += pick["found"]
    assert checked > 0
