"""fixed-chunks mode: round k sends chunk k of the sender's raw log, and nothing else."""

from experiments.protocol.messaging import (
    CHUNK_MESSAGE_TYPE,
    _send_fixed_chunk,
    fixed_chunk_for_round,
    raw_log_chunks,
)
from experiments.protocol.state import agent_state, create_channel_state, reset_message_delivery

SECRET = "PRIVATE-REASONING-MUST-NOT-LEAK"


def _state(raw_log: list[dict]) -> dict:
    state = create_channel_state("ep", comm_mode="fixed-chunks")
    alice = agent_state(state, "alice")
    alice["private_raw_log"] = raw_log
    # Anything else the agent holds must never reach the channel.
    alice["reasoning"] = SECRET
    alice["notes"] = SECRET
    return state


def _long_log() -> list[dict]:
    return [
        {"seq": 1, "tool": "query_database", "arguments": {"sql": "SELECT " + "x, " * 200},
         "result": {"success": True, "rows": [{"id": f"R{i:04d}"} for i in range(80)]}},
        {"seq": 2, "tool": "save_final_answer", "arguments": {"answer": "done", "reasoning": "y" * 300},
         "result": {"success": True}},
    ]


def _run_rounds(state: dict, rounds: int) -> list[dict]:
    sent = []
    for round_index in range(rounds):
        state["round"] = round_index
        reset_message_delivery(state, "alice")
        sent.append(_send_fixed_chunk(state, "alice", round_index))
    return sent


def test_round_k_sends_chunk_k_verbatim():
    state = _state(_long_log())
    chunks = raw_log_chunks(state, "alice")
    assert len(chunks) >= 5
    results = _run_rounds(state, 5)

    inbox = agent_state(state, "bob")["inbox"]
    assert [m["content"] for m in inbox] == chunks[:5]
    assert [r["chunk_id"] for r in results] == [1, 2, 3, 4, 5]
    assert all(r["success"] for r in results)

    events = [e for e in state["events"] if e["tool"] == "send_message"]
    assert [e["chunk_id"] for e in events] == [1, 2, 3, 4, 5]
    assert all(e["sent_by_runner"] and e["message_type"] == CHUNK_MESSAGE_TYPE for e in events)
    assert [e["round"] for e in events] == [0, 1, 2, 3, 4]


def test_nothing_but_chunk_text_reaches_the_channel():
    state = _state(_long_log())
    _run_rounds(state, 5)
    inbox = agent_state(state, "bob")["inbox"]
    assert len(inbox) == 5
    assert all(set(m) == {"from", "to", "content", "round", "message_type"} for m in inbox)
    assert all(SECRET not in m["content"] for m in inbox)
    # The sender's own inbox stays empty: nothing is echoed back.
    assert agent_state(state, "alice")["inbox"] == []


def test_short_log_resends_last_chunk():
    state = _state([{"seq": 1, "tool": "read_code", "arguments": {}, "result": {"content": "z" * 250}}])
    chunks = raw_log_chunks(state, "alice")
    assert len(chunks) == 2
    assert [fixed_chunk_for_round(state, "alice", k)[0] for k in range(5)] == [1, 2, 2, 2, 2]
    _run_rounds(state, 5)
    assert [m["content"] for m in agent_state(state, "bob")["inbox"]] == [chunks[0]] + [chunks[1]] * 4


def test_empty_log_is_still_one_verbatim_chunk():
    state = _state([])
    assert fixed_chunk_for_round(state, "alice", 0) is not None  # "[]" is a one-chunk log
    state["agents"]["alice"]["private_raw_log"] = []
    chunks = raw_log_chunks(state, "alice")
    # json.dumps([]) is "[]": the runner still sends only verbatim log text.
    assert chunks == ["[]"]
