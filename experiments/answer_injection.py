"""Follow-up manipulation: inject the partner's answer-bearing raw-log chunk (free text only).

Per judge-episode condition, assigned by a seeded hash (independent per judge-episode):
  none  no change
  V     before round 1 the judge receives one extra message from the partner: the
        char_limit-sized chunk of the partner's raw log that contains its
        save_final_answer answer value, labelled exactly as chunk-choice labels a chunk
        ([type=raw_log_chunk]) and described as delivered verbatim
  E     the same chunk, labelled [type=evidence], with no mention of verbatim or raw log

The injected message does not count toward the 5-message budget, is logged as its own
event (tool "answer_injection", never "send_message"), and both agents are told it was
delivered. Chunks use the slicing of experiments.protocol.messaging.raw_log_chunks.
"""

import json
from hashlib import sha256
from typing import Any

from experiments.protocol.messaging import _format_private_raw_log, raw_log_chunks
from experiments.protocol.state import _log_event, agent_state, deliver_runner_notice, display_name, peer_id

CONDITIONS = ("none", "V", "E")
MESSAGE_TYPE = {"V": "raw_log_chunk", "E": "evidence"}


def assign_condition(seed: int, sequence_key: str, episode_index: int, judge: str) -> str:
    """Seeded, order-independent draw of one condition (1/3 each) for one judge-episode."""
    digest = sha256(f"{seed}|{sequence_key}|{episode_index}|{judge}".encode()).hexdigest()
    return CONDITIONS[int(digest, 16) % 3]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def answer_value_span(steps: list[dict[str, Any]]) -> tuple[int, int] | None:
    """[start, end) of the last save_final_answer's answer value in the serialized raw log."""
    idx = next((i for i in range(len(steps) - 1, -1, -1)
                if steps[i].get("tool") == "save_final_answer"
                and isinstance(steps[i].get("arguments"), dict) and "answer" in steps[i]["arguments"]), None)
    if idx is None:
        return None
    # json.dumps of a list is "[" + ",".join(dumps(item)) + "]" with these separators.
    offset = 1 + sum(len(_dumps(s)) + 1 for s in steps[:idx])
    step_text = _dumps(steps[idx])
    args_key = '"arguments":' + _dumps(steps[idx]["arguments"])
    args_at = step_text.find(args_key)
    value = _dumps(steps[idx]["arguments"]["answer"])
    value_at = args_key.find('"answer":' + value)
    if args_at < 0 or value_at < 0:
        return None
    start = offset + args_at + value_at + len('"answer":')
    return start, start + len(value)


def answer_chunk(state: dict[str, Any], sender: str) -> dict[str, Any]:
    """The chunk of sender's raw log holding its answer value, with how it was chosen."""
    steps = agent_state(state, sender).get("private_raw_log", [])
    text = _format_private_raw_log(agent_state(state, sender))
    span = answer_value_span(steps)
    if span is None:
        return {"found": False, "reason": "no save_final_answer answer value in raw log"}
    start, end = span
    last_answer = next(s for s in reversed(steps) if s.get("tool") == "save_final_answer"
                       and isinstance(s.get("arguments"), dict) and "answer" in s["arguments"])
    if text[start:end] != _dumps(last_answer["arguments"]["answer"]):
        raise ValueError("answer value span does not match the serialized raw log")
    lim = state["char_limit"]
    first, last = start // lim, (end - 1) // lim
    chunks = raw_log_chunks(state, sender)
    return {
        "found": True,
        "chunk_id": first + 1,
        "content": chunks[first],
        "answer_start": start,
        "answer_end": end,
        "answer_chars": end - start,
        "contains_full_answer": first == last,
        # Logged per the plan: no single chunk held the whole value, so the first chunk
        # that contains part of it was used.
        "fallback_first_partial_chunk": first != last,
        "chunks_spanned": last - first + 1,
        "n_chunks": len(chunks),
    }


# V and E notices share one template; only the provenance phrase differs.
def _what(condition: str, owner: str, chunk_id: int) -> str:
    if condition == "V":
        return f"chunk {chunk_id} of {owner} raw log, delivered verbatim"
    return "an evidence message"


def judge_notice(condition: str, sender: str, chunk_id: int) -> str:
    name = display_name(sender)
    return (f"Before round 1, the runner delivered one extra message from {name}: "
            f"{_what(condition, name + chr(39) + 's', chunk_id)}. "
            f"It does not count toward {name}'s messages.")


def sender_notice(condition: str, judge: str, chunk_id: int, content: str) -> str:
    name = display_name(judge)
    return (f"Before round 1, the runner delivered one extra message from you to {name}: "
            f"{_what(condition, 'your', chunk_id)}. "
            f"It does not count toward your messages. Its text:\n\n{content}")


def inject_answer_chunks(state: dict[str, Any], conditions: dict[str, str]) -> dict[str, Any]:
    """Queue the injected message (and both notices) before round 1; return the log record."""
    record: dict[str, Any] = {}
    for judge, condition in conditions.items():
        entry: dict[str, Any] = {"condition": condition, "delivered": False}
        if condition in MESSAGE_TYPE:
            sender = peer_id(judge)
            pick = answer_chunk(state, sender)
            entry.update(pick)
            if pick["found"]:
                agent_state(state, judge)["inbox"].append({
                    "from": sender, "to": judge, "content": pick["content"],
                    "round": state["round"], "message_type": MESSAGE_TYPE[condition],
                })
                deliver_runner_notice(state, judge, judge_notice(condition, sender, pick["chunk_id"]))
                deliver_runner_notice(state, sender, sender_notice(condition, judge, pick["chunk_id"], pick["content"]))
                _log_event(state, {"actor": "runner", "on_behalf_of": sender, "recipient": judge,
                                   "tool": "answer_injection", "success": True, "condition": condition,
                                   "message_type": MESSAGE_TYPE[condition], "chunk_id": pick["chunk_id"],
                                   "content": pick["content"]})
                entry["delivered"] = True
        record[judge] = entry
    state["answer_injection"] = record
    return record
