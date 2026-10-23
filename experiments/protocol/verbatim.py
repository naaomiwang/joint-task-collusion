"""Verbatim communication mode: messages made only of exact excerpts of the sender's raw log.

A message is one or more excerpts. Each excerpt must be an exact substring of the sender's
raw log after whitespace normalization (runs of whitespace collapse to one space, ends are
trimmed). The raw log is matched both as the serialized string get_log returns and with its
JSON string escapes decoded (\\n, \\t, \\", \\\\, \\uXXXX), because an agent may copy either
form; nothing else is relaxed, so edits and ellipses joining separate passages fail. The
harness joins the excerpts with EXCERPT_DELIMITER and delivers the result through the normal
channel (char limit applies to the joined text), labelled raw_log_excerpt. A rejected
message is logged and does not use up the round (see VERBATIM_ATTEMPTS).
"""

import re
from typing import Any

from experiments.protocol.errors import error_string
from experiments.protocol.messaging import _format_private_raw_log, _reject_message, _send_message
from experiments.protocol.state import agent_state

VERBATIM_MESSAGE_TYPE = "raw_log_excerpt"
EXCERPT_DELIMITER = " ¦ "
# One first attempt plus 3 retries per round; then the round is skipped.
VERBATIM_ATTEMPTS = 4

_ESC = {"n": " ", "t": " ", "r": " ", '"': '"', "\\": "\\", "/": "/", "b": " ", "f": " "}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def decode_json_escapes(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "u" and i + 5 < n:
                try:
                    out.append(chr(int(text[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            if nxt in _ESC:
                out.append(_ESC[nxt])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def log_views(raw_log: str) -> tuple[str, str]:
    return normalize(raw_log), normalize(decode_json_escapes(raw_log))


def is_verbatim(excerpt: str, views: tuple[str, str]) -> bool:
    e = normalize(excerpt)
    return bool(e) and any(e in v for v in views)


def _send_verbatim(state: dict[str, Any], actor: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate every excerpt against the sender's raw log, then deliver them joined."""
    excerpts = arguments.get("excerpts")
    error = None
    if set(arguments) != {"excerpts"}:
        error = "send_message takes exactly one argument, excerpts"
    elif not isinstance(excerpts, list) or not excerpts or not all(isinstance(x, str) for x in excerpts):
        error = "excerpts must be a non-empty list of strings"
    else:
        views = log_views(_format_private_raw_log(agent_state(state, actor)))
        bad = [i + 1 for i, x in enumerate(excerpts) if not is_verbatim(x, views)]
        if bad:
            error = (f"excerpt {', '.join(map(str, bad))} is not an exact substring of your raw log "
                     "(only whitespace may differ; no edits or ellipses)")
    if error is not None:
        result = _reject_message(
            state=state, actor=actor, content=repr(arguments.get("excerpts", arguments)),
            message_type=VERBATIM_MESSAGE_TYPE, error=error_string("MessageError", error),
        )
        state["events"][-1]["verbatim_rejection"] = True
        return result
    result = _send_message(state=state, actor=actor, content=EXCERPT_DELIMITER.join(excerpts),
                           message_type=VERBATIM_MESSAGE_TYPE)
    state["events"][-1]["excerpt_count"] = len(excerpts)
    if not result.get("success"):
        state["events"][-1]["verbatim_rejection"] = True
    return result
