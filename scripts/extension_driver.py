"""Driver for the Luna extension runs (results/luna_extension/run_plan.json). Started by
scripts/launch_extension.sh; safe to restart at any time.

- Resumable: a run whose run.json has 10 episodes for its manifest and comm mode is skipped. A
  run folder that exists but is incomplete is moved aside to results/xa/ (kept, its spend still
  counted) and that run restarts from scratch.
- Before starting anything: aborts if OpenRouter's canonical slug for openai/gpt-6-luna is not
  the pre-registered one, or if spend so far + the estimate for the remaining runs exceeds the
  cap. Before each run: stops if spend + that arm's worst-case run cost would exceed the cap.
  During a run: kills it once spend reaches the cap. After each run: stops if any call reports a
  model or provider other than the sequence 6-11 runs.
- Spend = sum of billed cost_usd in every llm_usage.jsonl under results/x and results/xa.
- Never prints outcomes. The API key comes only from the repo's .env, loaded by the runner.

    .venv/Scripts/python.exe scripts/extension_driver.py [--plan-only]
Exit codes: 0 all done · 2 refused to start (check failed) · 3 cap reached · 4 model changed ·
5 a run failed · 6 another driver is running.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAN = json.loads((REPO / "results/luna_extension/run_plan.json").read_text(encoding="utf-8"))
LOG = REPO / "results/luna_extension/run.log"
PIDFILE = REPO / "results/luna_extension/driver.pid"
CAP = 24.0
CONFIG = "configs/luna_free_text.yaml"  # same settings for every arm; --comm-mode and --output-dir override
EXPECTED_COST = {"free-text": 0.377, "chunk-choice": 0.807, "verbatim": 0.471}
WORST_COST = {"free-text": 0.45, "chunk-choice": 0.95, "verbatim": 0.70}
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def spent() -> float:
    total = 0.0
    for root in ("results/x", "results/xa"):
        for p in glob.glob(str(REPO / root / "**" / "llm_usage.jsonl"), recursive=True):
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        total += float(json.loads(line).get("cost_usd") or 0)
                    except ValueError:
                        pass
    return total


def run_dirs(run: dict) -> list[Path]:
    out = REPO / PLAN["output_dirs"][run["arm"]] / "openai-gpt-6-luna"
    return [p for p in out.glob(f"*_rep{run['sequence']}_*") if p.is_dir()]


def manifest_of(run: dict) -> str:
    return f"rep{run['sequence']:03d}_sampled_manifest.json"


def finished(run: dict) -> Path | None:
    for d in run_dirs(run):
        p = d / "run.json"
        if not p.exists():
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rc = r["run_config"]
        if (len(r.get("results", [])) == 10 and rc.get("manifest", "").endswith(manifest_of(run))
                and "task_sequences_luna15" in rc.get("manifest", "") and rc.get("comm_mode") == run["arm"]):
            return d
    return None


def set_aside(run: dict) -> None:
    for d in run_dirs(run):
        if finished(run) == d:
            continue
        dest = REPO / "results/xa" / f"{run['arm'][0]}{run['sequence']:02d}_{datetime.now():%Y%m%d%H%M%S}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dest))
        log(f"moved incomplete run {d.name[:60]}... to {dest.relative_to(REPO)} (spend still counted)")


def canonical_slug() -> str | None:
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as resp:
            data = json.load(resp)["data"]
        return next((m.get("canonical_slug") for m in data if m["id"] == "openai/gpt-6-luna"), None)
    except Exception as exc:  # network failure: cannot verify, so refuse
        log(f"could not read the OpenRouter model list: {exc!r}")
        return None


def runner_command(run: dict) -> str:
    cmd = [PY, "-m", "experiments", "--config", CONFIG, "--task-sequence-record", PLAN["manifests"],
           "--comm-mode", run["arm"], "--repeats", "1", "--start-index", str(run["sequence"]),
           "--output-dir", PLAN["output_dirs"][run["arm"]], "--dry-run", "--no-judge"]
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=True, env=ENV).stdout
    lines = [ln[2:] for ln in out.splitlines() if ln.startswith("$ ")]
    assert len(lines) == 1 and manifest_of(run) in lines[0] and "task_sequences_luna15" in lines[0], lines
    return lines[0]


def model_ok(d: Path) -> bool:
    exp = PLAN["expected_model"]
    r = json.loads((d / "run.json").read_text(encoding="utf-8"))
    seen = {(u.get("response_model"), u.get("response_provider")) for e in r["results"] for u in e.get("llm_usage", [])}
    if seen != {(exp["response_model"], exp["response_provider"])}:
        log(f"model identity changed in {d.name[:60]}...: {sorted(seen, key=str)}")
        return False
    return True


def other_driver_alive() -> bool:
    if not PIDFILE.exists():
        return False
    pid = PIDFILE.read_text().strip()
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
        return pid in out and "python" in out.lower()
    return Path(f"/proc/{pid}").exists() or subprocess.run(["ps", "-p", pid], capture_output=True).returncode == 0


def kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def main() -> int:
    plan_only = "--plan-only" in sys.argv
    if not plan_only and other_driver_alive():
        log("another driver is running (results/luna_extension/driver.pid); not starting")
        return 6
    todo = [r for r in PLAN["runs"] if finished(r) is None]
    now = spent()
    estimate = now + sum(EXPECTED_COST[r["arm"]] for r in todo)
    log(f"plan: {len(PLAN['runs'])} runs, {len(PLAN['runs']) - len(todo)} finished, {len(todo)} to run; "
        f"spent ${now:.4f}; spent + estimate for remaining ${estimate:.2f}; cap ${CAP:.2f}")
    slug = canonical_slug()
    if slug != PLAN["expected_model"]["canonical_slug"]:
        log(f"REFUSE: canonical slug is {slug!r}, pre-registered {PLAN['expected_model']['canonical_slug']!r}")
        return 2
    if estimate > CAP:
        log(f"REFUSE: estimate ${estimate:.2f} exceeds cap ${CAP:.2f}")
        return 2
    if plan_only:
        for r in todo:
            log(f"would run sequence {r['sequence']} {r['arm']}")
        return 0
    PIDFILE.write_text(str(os.getpid()))
    try:
        for r in todo:
            set_aside(r)
            now = spent()
            if now + WORST_COST[r["arm"]] > CAP:
                log(f"STOP before sequence {r['sequence']} {r['arm']}: spent ${now:.4f} + ${WORST_COST[r['arm']]} > cap")
                return 3
            cmd = runner_command(r)
            log(f"start sequence {r['sequence']} {r['arm']} (spent ${now:.4f})")
            stamp = f"{r['arm'][0]}{r['sequence']:02d}"
            with open(REPO / f"results/luna_extension/runner_{stamp}.log", "a", encoding="utf-8") as fh:
                proc = subprocess.Popen(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=ENV)
                while proc.poll() is None:
                    time.sleep(15)
                    if spent() >= CAP:
                        kill_tree(proc)
                        log(f"KILLED sequence {r['sequence']} {r['arm']}: spend reached cap")
                        return 3
            done = finished(r)
            if proc.returncode != 0 or done is None:
                log(f"FAILED sequence {r['sequence']} {r['arm']} (exit {proc.returncode}); see results/luna_extension/runner_{stamp}.log")
                return 5
            if not model_ok(done):
                return 4
            log(f"done sequence {r['sequence']} {r['arm']} (spent ${spent():.4f})")
        log(f"ALL DONE: spent ${spent():.4f}")
        return 0
    finally:
        PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
