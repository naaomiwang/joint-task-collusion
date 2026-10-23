"""Mock dry run of the three arms (free text, chunk-choice, verbatim). No API calls.

Rebuilds one stored judge-episode (free text, sequence 8, episode 7; Alice judges Bob) and runs
the real communication and verdict phases under each comm mode with a mock model, then diffs
the harness-authored text the judge sees: system prompt, send_message tool, round instructions,
incoming message headers and the verdict prompt. Writes results/luna_extension/dry_run_arms.md.

    PYTHONUTF8=1 .venv/Scripts/python.exe analysis/final/dry_run_arms.py
"""

import difflib
import glob
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import experiments.episode_runner as er  # noqa: E402
from experiments.models import AgentRuntime, EpisodeRunConfig  # noqa: E402
from experiments.prompts.system import initial_agent_messages  # noqa: E402
from experiments.protocol.messaging import _send_chunk, _send_message  # noqa: E402
from experiments.protocol.state import agent_state, create_channel_state, reset_message_delivery  # noqa: E402
from experiments.protocol.submissions import _submit_verdict  # noqa: E402
from experiments.protocol.verbatim import _send_verbatim  # noqa: E402
from experiments.tool_schemas import get_tool_schemas  # noqa: E402

OUT = REPO / "results" / "luna_extension"
ARMS = ("free-text", "chunk-choice", "verbatim")


def mock(*, runtime, state, phase, round_index=None, **_):
    a = runtime.agent_id
    if phase != "communication":
        _submit_verdict(state, a, "accept", "<mock verdict reasoning>")
        return True
    reset_message_delivery(state, a)
    mode = state["comm_mode"]
    if mode == "chunk-choice":
        return _send_chunk(state=state, actor=a, arguments={"chunk_id": 1})["success"]
    if mode == "verbatim":
        return _send_verbatim(state, a, {"excerpts": ['"tool":"read_code"']})["success"]
    return _send_message(state, a, f"<mock {a} message, round {round_index + 1}>", "evidence")["success"]


def render(mode: str, e: dict) -> list[str]:
    state = create_channel_state("dry", comm_mode=mode)
    for a in ("alice", "bob"):
        agent_state(state, a)["private_raw_log"] = e["agents"][a]["private_raw_log"]
    prepared = SimpleNamespace(task_type=e["task_type"], state=state, agents={
        a: SimpleNamespace(judging_prompt=e["agents"][a]["judging_prompt"], verdict_prompt=e["agents"][a]["verdict_prompt"])
        for a in ("alice", "bob")})
    runtimes = {a: AgentRuntime(agent_id=a, config=None, messages=[]) for a in ("alice", "bob")}
    config = EpisodeRunConfig(comm_mode=mode, max_rounds=5, verbose=False)
    kw = dict(state=state, runtimes=runtimes, episode_id="dry", config=config, reasoning_traces=[], usage_records=[])
    er._run_agent_attempts = mock
    er._run_communication_phase(prepared=prepared, **kw)
    er._run_verdict_phase(prepared=prepared, **kw)
    lines = ["# system prompt"] + initial_agent_messages(agent_id="alice", max_rounds=5, reward_objective=True,
                                                         comm_mode=mode)[0]["content"].splitlines()
    tools = get_tool_schemas(e["task_type"], "communication", peer="bob", comm_mode=mode)
    send = next(t for t in tools if t["function"]["name"] == "send_message")
    lines += ["# send_message tool"] + json.dumps(send, ensure_ascii=False, indent=1).splitlines()
    lines.append("# judge context (harness text; message bodies replaced by <body>)")
    for m in runtimes["alice"].messages:
        c = m.get("content")
        if not isinstance(c, str):
            continue
        if c.startswith("[round="):  # incoming: keep only headers
            lines += [ln for ln in c.splitlines() if ln.startswith("[round=")] + ["<body>"]
        elif "chunk 1:" in c:  # full chunk listing: keep the instruction, drop the listing
            lines += [ln for ln in c.splitlines() if not re.match(r"chunk \d+:", ln)]
        else:
            lines += c.splitlines()
    return lines


def main() -> int:
    path = next(p for p in glob.glob(str(REPO / "results/l/f/openai-gpt-6-luna/*/run.json")) if "_rep8_" in p)
    e = json.load(open(path, encoding="utf-8"))["results"][6]
    R = {m: render(m, e) for m in ARMS}
    L = ["# Dry run: free text vs chunk-choice vs verbatim (mock model, no API calls)", "",
         "Stored judge-episode: free text, sequence 8, episode 7 (Alice judges Bob). Only lines that differ "
         "between arms are shown; message bodies are replaced by `<body>`.", ""]
    for a, b in (("free-text", "chunk-choice"), ("free-text", "verbatim"), ("chunk-choice", "verbatim")):
        L += [f"## {a} → {b}", "", "```diff"]
        L += [ln for ln in difflib.unified_diff(R[a], R[b], lineterm="", n=0) if not ln.startswith(("---", "+++", "@@"))]
        L += ["```", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dry_run_arms.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
