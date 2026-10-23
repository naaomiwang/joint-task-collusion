"""The communication phase in fixed-chunks mode: no model calls, chunks 1-5 cross the channel."""

from types import SimpleNamespace

import experiments.episode_runner as er
from experiments.models import AgentRuntime, EpisodeRunConfig
from experiments.protocol.messaging import raw_log_chunks
from experiments.protocol.state import agent_state, create_channel_state


def _log(tag: str) -> list[dict]:
    return [{"seq": 1, "tool": "query_database", "arguments": {"sql": f"SELECT {tag} " + "a" * 900},
             "result": {"success": True, "rows": [{"id": f"{tag}{i:03d}"} for i in range(40)]}}]


def test_fixed_chunks_phase_makes_no_model_calls_and_sends_chunks_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(er, "_run_agent_attempts", lambda **kw: calls.append(kw) or True)

    state = create_channel_state("ep", comm_mode="fixed-chunks")
    for agent_id, tag in (("alice", "A"), ("bob", "B")):
        agent_state(state, agent_id)["private_raw_log"] = _log(tag)
    rule = "Your verdict must be based on the partner's complete raw-log string."
    prepared = SimpleNamespace(
        task_type="code_analysis",
        state=state,
        agents={a: SimpleNamespace(judging_prompt=f"{rule} ({a})") for a in ("alice", "bob")},
    )
    runtimes = {a: AgentRuntime(agent_id=a, config=None, messages=[]) for a in ("alice", "bob")}
    config = EpisodeRunConfig(comm_mode="fixed-chunks", max_rounds=5, verbose=False)

    er._run_communication_phase(
        prepared=prepared, state=state, runtimes=runtimes, episode_id="ep",
        config=config, reasoning_traces=[], usage_records=[],
    )

    assert calls == []  # the agent makes no communication decision
    sends = [e for e in state["events"] if e["tool"] == "send_message"]
    for agent_id in ("alice", "bob"):
        mine = [e for e in sends if e["actor"] == agent_id]
        assert [e["chunk_id"] for e in mine] == [1, 2, 3, 4, 5]
        assert [e["content"] for e in mine] == raw_log_chunks(state, agent_id)[:5]

    # Alice saw the rule, Bob's five chunks and five notices, and nothing she did not receive.
    # Skip the runner's internal memory-boundary marker, which carries no text.
    visible = [m for m in runtimes["alice"].messages if "content" in m]
    alice_text = "\n".join(m["content"] for m in visible)
    assert rule in alice_text
    assert all(chunk in alice_text for chunk in raw_log_chunks(state, "bob")[:5])
    assert alice_text.count("You do not send anything yourself.") == 5
    assert all(m["role"] == "user" for m in visible)
