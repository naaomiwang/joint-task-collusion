"""Build task/task_sequences_luna15: sequences 1-11 copied unchanged, 12-15 newly sampled.

The original sampler is not in this repo; only its record and invariants are
(task/task_sequences_50x10/sampled_manifest_record.json). This re-implements those invariants:
10 episodes; each episode's task type drawn uniformly from the three types; two distinct tasks of
that type drawn uniformly without replacement; no task twice in a run; one task per code
spec_key per run; every pair passes experiments.tasks.validate_task_pair; all three task types
appear (otherwise the whole sequence is redrawn). Seeds are new: "task-sequence-luna15:NNN".

rep001-rep005 are copied from task/task_sequences_5x10 (the original sequence 1-5 runs; byte
identical to task_sequences_25x10) and rep006-rep011 from task/task_sequences_25x10 (the
sequence 6-11 runs), so --start-index k always means sequence k.

    python analysis/final/sample_sequences.py        (refuses to overwrite)
"""

import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from experiments.tasks import _read_task_pool, task_spec_key, task_type_of, validate_task_pair  # noqa: E402

OUT = REPO / "task" / "task_sequences_luna15"
TYPES = ("code_analysis", "data_search", "record_extraction")


def sample(seed: str, pool: list[dict]) -> list[tuple[dict, dict]]:
    rng = random.Random(seed)
    by_type = {t: sorted((x for x in pool if task_type_of(x) == t), key=lambda x: x["task_id"]) for t in TYPES}
    while True:
        used, specs, pairs = set(), set(), []
        ok = True
        for _ in range(10):
            t = rng.choice(TYPES)
            cand = [x for x in by_type[t] if x["task_id"] not in used and not (task_spec_key(x) and task_spec_key(x) in specs)]
            picked = []
            for _ in range(200):
                if len(cand) < 2:
                    break
                a, b = rng.sample(cand, 2)
                try:
                    validate_task_pair(a, b)
                    picked = [a, b]
                    break
                except ValueError:
                    continue
            if not picked:
                ok = False
                break
            for x in picked:
                used.add(x["task_id"])
                if task_spec_key(x):
                    specs.add(task_spec_key(x))
            pairs.append(tuple(picked))
        if ok and {task_type_of(p[0]) for p in pairs} == set(TYPES):
            return pairs


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=False)
    for i in range(1, 6):
        shutil.copyfile(REPO / f"task/task_sequences_5x10/rep{i:03d}_sampled_manifest.json", OUT / f"rep{i:03d}_sampled_manifest.json")
    for i in range(6, 12):
        shutil.copyfile(REPO / f"task/task_sequences_25x10/rep{i:03d}_sampled_manifest.json", OUT / f"rep{i:03d}_sampled_manifest.json")
    pool = _read_task_pool(REPO)
    runs = []
    for i in range(12, 16):
        seed = f"task-sequence-luna15:{i:03d}"
        pairs = sample(seed, pool)
        (OUT / f"rep{i:03d}_sampled_manifest.json").write_text(
            json.dumps({"pairs": [{"tasks": [a["task_id"], b["task_id"]]} for a, b in pairs]}, indent=1) + "\n", encoding="utf-8")
        code = [x for p in pairs for x in p if task_type_of(x) == "code_analysis"]
        runs.append({"rep": i, "generation_seed": seed,
                     "pairs_by_task_type": dict(Counter(task_type_of(a) for a, _ in pairs)),
                     "code_expected_verdicts": dict(Counter(str(x.get("expected_verdict")) for x in code)),
                     "pairs": [{"episode": k + 1, "task_type": task_type_of(a), "task_ids": [a["task_id"], b["task_id"]]}
                               for k, (a, b) in enumerate(pairs)]})
    record = {"description": __doc__.split("\n\n")[0] + " rep001-011 are unchanged copies; rep012-015 sampled here.",
              "copied": {"rep001-rep005": "task/task_sequences_5x10", "rep006-rep011": "task/task_sequences_25x10"},
              "sampler": "analysis/final/sample_sequences.py", "new_runs": runs}
    (OUT / "sampled_manifest_record.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    for r in runs:
        print(r["rep"], r["generation_seed"], r["pairs_by_task_type"], r["code_expected_verdicts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
