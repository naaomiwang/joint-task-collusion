"""Inter-agent messaging and per-agent raw-log retrieval."""

import json
from typing import Any

from experiments.protocol.errors import error_string
from experiments.protocol.state import _log_event, agent_state, peer_id


def _send_message(
    state: dict[str, Any],
    actor: str,
    content: str,
    message_type: str = "other",
) -> dict[str, Any]:
    slot = agent_state(state, actor)
    if slot["delivered"]:
        return _reject_message(
            state=state,
            actor=actor,
            content=content,
            message_type=message_type,
            error=error_string(
                "MessageError",
                f"{actor} already sent its one message for this round",
            ),
        )

    if (
        state["throttled"]
        and len(content) > state["char_limit"]
    ):
        return _reject_message(
            state=state,
            actor=actor,
            content=content,
            message_type=message_type,
            error=error_string(
                "MessageError", f"exceeds {state['char_limit']} char limit"
            ),
        )

    slot["delivered"] = True
    recipient = peer_id(actor)
    # Keep the originating 0-based round; display tags add one.
    payload: dict[str, Any] = {
        "from": actor,
        "to": recipient,
        "content": content,
        "round": state["round"],
    }
    payload["message_type"] = message_type
    # Deliver immediately so the peer can reply within the same round.
    agent_state(state, recipient)["inbox"].append(payload)

    result = {"success": True, "chars_sent": len(content)}
    event = {
        "actor": actor,
        "recipient": recipient,
        "tool": "send_message",
        "success": True,
        "content": content,
    }
    event["message_type"] = message_type
    _log_event(state, event)
    return result


def _reject_message(
    *,
    state: dict[str, Any],
    actor: str,
    content: str,
    message_type: str,
    error: str,
) -> dict[str, Any]:
    result = {"success": False, "error": error, "chars_sent": 0}
    # Record the complete attempted message, including refused deliveries.
    event = {
        "actor": actor,
        "recipient": peer_id(actor),
        "tool": "send_message",
        "success": False,
        "error": error,
        "content": content,
    }
    event["message_type"] = message_type
    _log_event(state, event)
    return result


COMM_MODES = ("free-text", "chunk-choice", "fixed-chunks")
CHUNK_MESSAGE_TYPE = "raw_log_chunk"


def raw_log_chunks(state: dict[str, Any], actor: str) -> list[str]:
    """Split the actor's raw log into fixed, non-overlapping chunks of char_limit chars.

    The string is the one get_log returns; chunk_id k is element k - 1.
    """
    raw_log = _format_private_raw_log(agent_state(state, actor))
    size = state["char_limit"]
    return [raw_log[start:start + size] for start in range(0, len(raw_log), size)]


def _send_chunk(
    state: dict[str, Any],
    actor: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Deliver one raw-log chunk verbatim; the agent supplies only its ID."""
    chunks = raw_log_chunks(state, actor)
    chunk_id = arguments.get("chunk_id")
    error = None
    if set(arguments) != {"chunk_id"}:
        error = "send_message takes exactly one argument, chunk_id"
    elif isinstance(chunk_id, bool) or not isinstance(chunk_id, int):
        error = "chunk_id must be an integer"
    elif not 1 <= chunk_id <= len(chunks):
        error = f"chunk_id must be between 1 and {len(chunks)}"
    if error is not None:
        return _reject_message(
            state=state,
            actor=actor,
            content=json.dumps(arguments, ensure_ascii=False),
            message_type=CHUNK_MESSAGE_TYPE,
            error=error_string("MessageError", error),
        )
    result = _send_message(
        state=state,
        actor=actor,
        content=chunks[chunk_id - 1],
        message_type=CHUNK_MESSAGE_TYPE,
    )
    # Record which chunk was sent on the logged event, delivered or not.
    state["events"][-1]["chunk_id"] = chunk_id
    if result.get("success"):
        result["chunk_id"] = chunk_id
    return result


def fixed_chunk_for_round(
    state: dict[str, Any], actor: str, round_index: int
) -> tuple[int, str] | None:
    """The chunk fixed-chunks mode sends in 0-based round ``round_index``.

    Round k sends chunk k; a log with fewer chunks resends its last chunk, so the
    channel only ever carries verbatim log text. None for an empty log.
    """
    chunks = raw_log_chunks(state, actor)
    if not chunks:
        return None
    chunk_id = min(round_index + 1, len(chunks))
    return chunk_id, chunks[chunk_id - 1]


def _send_fixed_chunk(
    state: dict[str, Any],
    actor: str,
    round_index: int,
) -> dict[str, Any]:
    """Deliver the round's fixed chunk verbatim; the agent makes no choice."""
    picked = fixed_chunk_for_round(state, actor, round_index)
    if picked is None:
        return _reject_message(
            state=state,
            actor=actor,
            content="",
            message_type=CHUNK_MESSAGE_TYPE,
            error=error_string("MessageError", "raw log is empty, so there is no chunk to send"),
        )
    chunk_id, content = picked
    result = _send_message(
        state=state,
        actor=actor,
        content=content,
        message_type=CHUNK_MESSAGE_TYPE,
    )
    # Record which chunk the runner sent, so the channel is auditable.
    state["events"][-1]["chunk_id"] = chunk_id
    state["events"][-1]["sent_by_runner"] = True
    if result.get("success"):
        result["chunk_id"] = chunk_id
    return result


def _format_private_raw_log(slot: dict[str, Any]) -> str:
    return json.dumps(
        slot.get("private_raw_log", []),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _get_log(state: dict[str, Any], actor: str) -> dict[str, Any]:
    """Return only the calling agent's raw log.

    The dispatch gate permits one retrieval per agent per episode.
    """
    slot = agent_state(state, actor)
    raw_log = _format_private_raw_log(slot)
    slot["private_raw_log_retrieved"] = True
    result = {
        "success": True,
        "raw_log": raw_log,
        "raw_log_chars": len(raw_log),
    }
    _log_event(
        state,
        {
            "actor": actor,
            "tool": "get_log",
            "success": True,
        },
    )
    return result
