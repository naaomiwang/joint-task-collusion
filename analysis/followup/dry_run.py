"""Dry run of the answer-injection follow-up with a mock model (no API calls).

Takes one stored judge-episode (free text, sequence 8, episode 7; Alice judges Bob), rebuilds
its channel state from the saved raw logs and prompts, and runs the real communication and
verdict phases of experiments/episode_runner.py under each condition. The mock model sends a
fixed placeholder message each round and submits a fixed verdict, so only the harness's own
text differs between conditions. Writes results/followup/dry_run.md.

    PYTHONUTF8=1 .venv/Scripts/python.exe analysis/followup/dry_run.py
"""

import glob
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import experiments.episode_runner as er  # noqa: E402
from experiments.models import AgentRuntime, EpisodeRunConfig  # noqa: E402
from experiments.protocol.messaging import _send_message  # noqa: E402
from experiments.protocol.state import agent_state, create_channel_state, reset_message_delivery  # noqa: E402
from experiments.protocol.submissions import _submit_verdict  # noqa: E402

SEQ, EP, JUDGE = 8, 7, "alice"
OUT = REPO / "results" / "followup"


def mock_attempts(*, runtime, state, phase, round_index=None, **_):
    """Stand-in for the model: one placeholder message per round, then ACCEPT."""
    if phase == "communication":
        reset_message_delivery(state, runtime.agent_id)
        text = f"<mock {runtime.agent_id} message, round {round_index + 1}>"
        return _send_message(state, runtime.agent_id, text, "evidence")["success"]
    _submit_verdict(state, runtime.agent_id, "accept", "<mock verdict reasoning>")
    return True


def stored_episode():
    path = next(p for p in glob.glob(str(REPO / "results/l/f/openai-gpt-6-luna/*/run.json"))
                if f"_rep{SEQ}_" in p)
    return json.load(open(path, encoding="utf-8"))["results"][EP - 1]


def run(condition: str, e: dict) -> dict:
    state = create_channel_state("dry", comm_mode="free-text")
    for a in ("alice", "bob"):
        agent_state(state, a)["private_raw_log"] = e["agents"][a]["private_raw_log"]
    # Each slot stores the prompts shown to that agent's judge (see results/prompt_framing.md).
    prepared = SimpleNamespace(task_type=e["task_type"], state=state, agents={
        a: SimpleNamespace(judging_prompt=e["agents"][a]["judging_prompt"],
                           verdict_prompt=e["agents"][a]["verdict_prompt"]) for a in ("alice", "bob")})
    runtimes = {a: AgentRuntime(agent_id=a, config=None, messages=[]) for a in ("alice", "bob")}
    conditions = {JUDGE: condition, "bob": "none"} if condition != "none" else {}
    config = EpisodeRunConfig(comm_mode="free-text", max_rounds=5, verbose=False, answer_injection=conditions)
    kw = dict(state=state, runtimes=runtimes, episode_id="dry", config=config, reasoning_traces=[], usage_records=[])
    er._run_communication_phase(prepared=prepared, **kw)
    er._run_verdict_phase(prepared=prepared, **kw)
    return {"judge": [m["content"] for m in runtimes[JUDGE].messages if "content" in m],
            "sender": [m["content"] for m in runtimes["bob"].messages if "content" in m],
            "record": state.get("answer_injection", {}).get(JUDGE),
            "sends": sum(1 for x in state["events"] if x["tool"] == "send_message" and x["success"])}


def turns(msgs: list[str]) -> list[tuple[str, str]]:
    """Label each message by the turn it belongs to, so conditions line up row by row."""
    out, rnd = [], 0
    for i, m in enumerate(msgs):
        if i == 0:
            out.append(("Peer brief + verdict policy", "*identical in all conditions; full text below*"))
        elif "of 5)." in m and m.startswith("Use the send_message tool"):
            rnd = int(m.split("(round ")[1].split(" ")[0])
            out.append((f"Round {rnd} instruction", m))
        elif m.startswith("[round="):
            out.append((f"Inbox before round {rnd + 1}" if rnd < 5 else "Inbox before verdict", m))
        else:
            out.append(("Verdict prompt", m))
    return out


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def main() -> int:
    import experiments.episode_runner as module
    module._run_agent_attempts = mock_attempts
    e = stored_episode()
    res = {c: run(c, e) for c in ("none", "V", "E")}
    n = max(len(r["judge"]) for r in res.values())
    rec = res["V"]["record"]
    L = ["# Dry run: answer injection (mock model, no API calls)", "",
         f"Stored judge-episode: free text, sequence {SEQ}, episode {EP} ({e['task_type']}); "
         f"judge = Alice, partner = Bob. The mock sends `<mock … message, round k>` each round and "
         f"submits ACCEPT, so every difference below comes from the harness.", "",
         f"Injected chunk: chunk {rec['chunk_id']} of {rec['n_chunks']} of Bob's raw log; answer value "
         f"{rec['answer_chars']} characters, fully inside the chunk: {rec['contains_full_answer']}. "
         f"Successful send_message calls per condition: "
         + ", ".join(f"{c} {r['sends']}" for c, r in res.items()) + " (budget unchanged).", "",
         "## Judge (Alice): everything she receives from the start of communication to the verdict prompt", "",
         "| Turn | none | V | E |", "|---|---|---|---|"]
    keyed = {c: turns(r["judge"]) for c, r in res.items()}
    order = list(dict.fromkeys(k for c in ("V", "none", "E") for k, _ in keyed[c]))
    for key in order:
        row = ["<br><br>".join(t for k, t in keyed[c] if k == key) or "*(nothing)*" for c in ("none", "V", "E")]
        L.append(f"| {key} | " + " | ".join(cell(x) for x in row) + " |")
    L += ["", "## Sender (Bob): his round-1 inbox", "", "| none | V | E |", "|---|---|---|"]
    first = []
    for c in ("none", "V", "E"):
        msgs = res[c]["sender"]
        idx = next(i for i, m in enumerate(msgs) if "round 1 of 5" in m)
        first.append(msgs[idx - 1] if idx and msgs[idx - 1].startswith("[round") else "(empty: no new message before his round-1 turn other than Alice's)")
    L.append("| " + " | ".join(cell(x) for x in first) + " |")
    L += ["", "## Peer brief and verdict policy (message 1, identical)", "", "```", res["none"]["judge"][0], "```", "",
          "## Injection log record (V)", "", "```json", json.dumps(rec, indent=1, ensure_ascii=False), "```"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dry_run.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
