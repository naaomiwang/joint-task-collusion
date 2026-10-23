"""Launch the follow-up under a spend cap (results/followup/PLAN.md, "Spend").

  smoke: sequence 21, seed 3, output results/followup/smoke, cap $0.50 (excluded from analysis)
  main:  sequences 1-20 from configs/followup_answer_injection.yaml, cap $10

Runner commands are taken verbatim from `python -m experiments --config ... --dry-run`, so
they are exactly what the config's repeats/start_index produce; they are run one sequence
at a time. Spend = sum of billed cost_usd in the output tree's llm_usage.jsonl files. A new
sequence starts only if spend + $0.45 (costliest stored free-text sequence) <= cap; a
watchdog polls every 10 s and kills the runner once spend reaches the cap. The API key comes
only from the repo's .env (the runner loads it; nothing here reads or prints it).

    .venv/Scripts/python.exe analysis/followup/launch.py smoke
    .venv/Scripts/python.exe analysis/followup/launch.py main
"""

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = "configs/followup_answer_injection.yaml"
MODES = {
    "smoke": {"cap": 0.50, "out": "results/followup/smoke",
              "extra": ["--repeats", "1", "--start-index", "21", "--answer-injection-seed", "3"]},
    "main": {"cap": 10.00, "out": "results/fu", "extra": []},
}
PER_SEQ_MAX = 0.45


def spent(out: str) -> float:
    total = 0.0
    for p in glob.glob(str(REPO / out / "**" / "llm_usage.jsonl"), recursive=True):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    total += float(json.loads(line).get("cost_usd") or 0)
                except ValueError:
                    pass
    return total


def runner_commands(mode: dict) -> list[str]:
    cmd = [sys.executable, "-m", "experiments", "--config", CONFIG, "--dry-run", "--no-judge",
           "--output-dir", mode["out"], *mode["extra"]]
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONUTF8": "1"}).stdout
    return [line[2:] for line in out.splitlines() if line.startswith("$ ")]


def main() -> int:
    name = sys.argv[1]
    mode = MODES[name]
    logs = REPO / "results" / "followup" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    commands = runner_commands(mode)
    print(f"[{name}] {len(commands)} sequence(s), cap ${mode['cap']:.2f}", flush=True)
    for i, command in enumerate(commands, start=1):
        now = spent(mode["out"])
        if now + PER_SEQ_MAX > mode["cap"]:
            print(f"[{name}] STOP before sequence {i}: spent ${now:.4f} + ${PER_SEQ_MAX} > cap", flush=True)
            return 3
        label = command.split("--run-label ")[1].split(" ")[0]
        log = logs / f"{name}_{i:02d}.log"
        print(f"[{name}] start {i}/{len(commands)} {label} at {time.strftime('%H:%M:%S')}, spent ${now:.4f}", flush=True)
        with open(log, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen(command, cwd=REPO, shell=False, stdout=fh, stderr=subprocess.STDOUT,
                                    env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
            while proc.poll() is None:
                time.sleep(10)
                if spent(mode["out"]) >= mode["cap"]:
                    proc.kill()
                    print(f"[{name}] KILLED sequence {i}: spend reached cap ${mode['cap']:.2f}", flush=True)
                    return 4
        print(f"[{name}] done {i}/{len(commands)} exit {proc.returncode} at {time.strftime('%H:%M:%S')}, "
              f"spent ${spent(mode['out']):.4f}", flush=True)
        if proc.returncode != 0:
            print(f"[{name}] FAILED sequence {i}; see {log}", flush=True)
            return 5
    print(f"[{name}] ALL DONE, spent ${spent(mode['out']):.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
