"""Progress of the Luna extension without outcomes: runs done/remaining, in progress, spend.
Writes results/luna_extension/RUN_STATE.md. Called by scripts/status.sh."""

import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import extension_driver as D  # noqa: E402


def main() -> int:
    done, todo, partial = [], [], []
    for r in D.PLAN["runs"]:
        if D.finished(r):
            done.append(r)
            continue
        todo.append(r)
        for d in D.run_dirs(r):
            p = d / "run.json"
            n = len(json.loads(p.read_text(encoding="utf-8")).get("results", [])) if p.exists() else 0
            partial.append(f"sequence {r['sequence']} {r['arm']}: {n}/10 episodes saved")
    alive = D.other_driver_alive()
    tail = D.LOG.read_text(encoding="utf-8").splitlines()[-1] if D.LOG.exists() else "(no log yet)"
    lines = [f"# Luna extension run state ({datetime.now():%Y-%m-%d %H:%M})", "",
             f"- Runs completed: {len(done)}/{len(D.PLAN['runs'])}",
             f"- Runs remaining: {len(todo)}" + (f" (next: sequence {todo[0]['sequence']} {todo[0]['arm']})" if todo else ""),
             f"- In progress / partial: {'; '.join(partial) if partial else 'none'}",
             f"- Spend so far (all attempts): ${D.spent():.4f} of ${D.CAP:.2f} cap",
             f"- Driver running: {'yes' if alive else 'no'}",
             f"- Last log line: {tail}", "",
             "No outcomes are shown here by design."]
    text = "\n".join(lines)
    (REPO / "results/luna_extension/RUN_STATE.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
