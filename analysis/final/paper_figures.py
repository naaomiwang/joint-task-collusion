"""Figures and per-sequence table for the paper (paper/figures/). Same 15-sequence data as run_all.py; no model calls.

  fig_timing.png            (a) collusive episodes by episode, (b) agents that have accepted at least once
  fig_ec_by_sequence.png    collusive episodes per sequence, per arm
  fig_chunk_choice.png      what chunk agents send by round; where chunks and verbatim excerpts come from in the log

    PYTHONUTF8=1 python analysis/final/paper_figures.py   -> also results/luna_extension/per_sequence.md
"""

import math
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "analysis/final"), str(REPO / "analysis/paper_metrics"), str(REPO / "analysis/chunk_rerun"),
                str(REPO / "analysis/released_2x2"), str(REPO)]
import make_figures as MF  # noqa: E402
import run_all as RA  # noqa: E402
from free_text_evidence import normalized_log  # noqa: E402
from informativeness import RawLog, answer_bearing  # noqa: E402
from experiments.protocol.verbatim import EXCERPT_DELIMITER  # noqa: E402

FIG = REPO / "paper/figures"
ARMS, NAME = RA.ARMS, RA.NAME
SEQS = list(range(1, 16))
# Same hues as Figure 1 in the paper; validated as a categorical set, with distinct markers as the secondary encoding.
COL = {"free": "#6A4FE0", "chunk": "#D9603A", "verbatim": "#168F64"}
MARK = {"free": "o", "chunk": "s", "verbatim": "^"}
INK, MUTED, GRID = "#222222", "#666666", "#E6E3EE"

plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "legend.frameon": False})


def style(ax):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def accepts(e, a):
    return MF.episode_verdicts(e).get(a) == "accept"


def joint(e):
    return accepts(e, "alice") and accepts(e, "bob")


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=200, facecolor="white")
    plt.close(fig)


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    runs = {arm: RA.load(d) for arm, d in RA.SOURCES["real"].items()}
    eps = {arm: {s: MF.ordered_episodes(runs[arm][s]) for s in SEQS} for arm in ARMS}

    # Collusive episodes per sequence.
    J = {a: [sum(joint(e) for e in eps[a][s]) for s in SEQS] for a in ARMS}
    U = {a: [sum(accepts(e, w) for e in eps[a][s] for w in ("alice", "bob")) for s in SEQS] for a in ARMS}
    fig, ax = plt.subplots(figsize=(6.8, 2.3))
    x = np.arange(1, 16)
    for k, a in enumerate(ARMS):
        ax.vlines(x + (k - 1) * 0.22, 0, J[a], color=COL[a], lw=2.2)
        ax.plot(x + (k - 1) * 0.22, J[a], MARK[a], color=COL[a], ms=5, mec="white", mew=0.8, label=NAME[a])
    ax.set_xticks(x); ax.set_xlabel("Task sequence"); ax.set_ylabel("Collusive episodes (of 10)")
    ax.set_ylim(0, 8); ax.set_xlim(0.4, 15.6); style(ax); ax.legend(ncol=3, loc="upper left", fontsize=8)
    save(fig, "fig_ec_by_sequence.png")

    # First ACCEPT by episode, per agent seat.
    first = {a: [] for a in ARMS}
    for a in ARMS:
        for s in SEQS:
            for w in ("alice", "bob"):
                first[a].append(next((i + 1 for i, e in enumerate(eps[a][s]) if accepts(e, w)), None))
    # Timing: (a) collusive episodes by episode, (b) agents that have accepted at least once.
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 2.4))
    for a in ARMS:
        y = [sum(joint(eps[a][s][i]) for s in SEQS) for i in range(10)]
        a1.plot(range(1, 11), y, marker=MARK[a], ms=5, lw=1.8, color=COL[a], mec="white", mew=1, label=f"{NAME[a]} ({sum(y)}/150)")
        y = [100 * sum(f is not None and f <= t for f in first[a]) / 30 for t in range(1, 11)]
        a2.step(range(1, 11), y, where="post", color=COL[a], lw=1.8)
        a2.plot(range(1, 11), y, MARK[a], color=COL[a], ms=4.5, mec="white", mew=0.8, label=NAME[a])
    a1.set_xticks(range(1, 11)); a1.set_xlabel("Episode"); a1.set_ylabel("Collusive episodes (of 15)")
    a1.set_ylim(0, 10); style(a1); a1.legend(loc="upper left", fontsize=8, ncol=1)
    a1.set_title("(a) Collusive episodes", fontsize=9, loc="left", color=INK)
    a2.set_xticks(range(1, 11)); a2.set_xlabel("Episode"); a2.set_ylabel("Agents that have accepted (%)")
    a2.set_ylim(0, 100); style(a2); a2.legend(loc="lower right", fontsize=8)
    a2.set_title("(b) Agents that have accepted at least once", fontsize=9, loc="left", color=INK)
    save(fig, "fig_timing.png")

    # What chunk agents send by round, and where chunks and excerpts come from.
    by_round = {r: [0, 0, 0] for r in range(1, 6)}  # sends, answer-bearing, repeats
    qpos = {"chunk": Counter(), "verbatim": Counter()}
    for s in SEQS:
        for e in eps["chunk"][s]:
            for w in ("alice", "bob"):
                raw = RawLog(e["agents"][w]["private_raw_log"]); n = math.ceil(len(raw.text) / 200); prev = []
                for m in e["events"]:
                    if m.get("tool") != "send_message" or not m.get("success") or m.get("actor") != w:
                        continue
                    cid = int(m["chunk_id"]); st = raw.locate(m["content"], (cid - 1) * 200)
                    tags = raw.tags_for(st, st + len(m["content"])) if st is not None else set()
                    r = by_round[m["round"] + 1]; r[0] += 1; r[1] += answer_bearing(tags); r[2] += cid in prev
                    prev.append(cid)
                    qpos["chunk"][min(int((cid - 1) / max(n - 1, 1) * 4), 3)] += 1
        for e in eps["verbatim"][s]:
            for m in e["events"]:
                if m.get("tool") != "send_message" or not m.get("success"):
                    continue
                raw = RawLog(e["agents"][m["actor"]]["private_raw_log"]); norm, mp = normalized_log(raw.text)
                for ex in m["content"].split(EXCERPT_DELIMITER):
                    ex = re.sub(r"\s+", " ", ex).strip()
                    i = norm.find(ex) if ex else -1
                    if i >= 0:
                        qpos["verbatim"][min(int(mp[i] / max(len(raw.text), 1) * 4), 3)] += 1
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 2.3))
    rs = list(range(1, 6))
    ab = [100 * by_round[r][1] / by_round[r][0] for r in rs]; rp = [100 * by_round[r][2] / by_round[r][0] for r in rs]
    a1.plot(rs, ab, marker="s", color=COL["chunk"], lw=1.8, ms=5, mec="white", mew=0.8)
    a1.plot(rs, rp, marker="D", color=COL["chunk"], lw=1.4, ls="--", ms=4.5, mec="white", mew=0.8)
    a1.annotate("carries answer content", (5, ab[-1]), xytext=(-4, 7), textcoords="offset points", ha="right", fontsize=8, color=INK)
    a1.annotate("repeats an earlier chunk", (3, rp[2]), xytext=(6, -12), textcoords="offset points", ha="left", fontsize=8, color=INK)
    a1.set_xticks(rs); a1.set_xlabel("Round"); a1.set_ylabel("Chunks sent (%)"); a1.set_ylim(0, 70); style(a1)
    a1.set_title("(a) Chunks by round", fontsize=9, loc="left", color=INK)
    qs = np.arange(4); w = 0.38
    for k, a in enumerate(("chunk", "verbatim")):
        tot = sum(qpos[a].values()); y = [100 * qpos[a][q] / tot for q in range(4)]
        a2.bar(qs + (k - 0.5) * w, y, w - 0.04, color=COL[a], label=f"{NAME[a]} (n = {tot:,})",
               hatch=None if a == "chunk" else "///", edgecolor="white", lw=0)
    a2.set_xticks(qs, ["1st", "2nd", "3rd", "4th"]); a2.set_xlabel("Quarter of the sender's raw log"); a2.set_ylabel("Share sent (%)")
    a2.set_ylim(0, 100); style(a2); a2.legend(fontsize=8, loc="upper left")
    a2.set_title("(b) Where content comes from", fontsize=9, loc="left", color=INK)
    save(fig, "fig_chunk_choice.png")

    # Per-sequence table.
    L = ["# Per-sequence results", "", "Collusive episodes (of 10) and individual ACCEPTs (of 20), per sequence and arm. "
         "Generated by `analysis/final/paper_figures.py`.", "", "| Sequence | EC free | EC chunks | EC verbatim | U free | U chunks | U verbatim |",
         "|---|---|---|---|---|---|---|"]
    for i, s in enumerate(SEQS):
        L.append(f"| {s} | " + " | ".join(str(J[a][i]) for a in ARMS) + " | " + " | ".join(str(U[a][i]) for a in ARMS) + " |")
    L.append("| Total | " + " | ".join(str(sum(J[a])) for a in ARMS) + " | " + " | ".join(str(sum(U[a])) for a in ARMS) + " |")
    L += ["", "First ACCEPT episode per seat (None = never): " + "; ".join(f"{NAME[a]} median "
          f"{np.median([f if f is not None else 11 for f in first[a]]):.0f}, never {sum(f is None for f in first[a])}/30" for a in ARMS),
          "", "Chunks by round (sends, answer-bearing, repeats): " + str(by_round),
          "", "Position quarters: " + str({a: dict(sorted(qpos[a].items())) for a in qpos})]
    text = "\n".join(L)
    (REPO / "results/luna_extension/per_sequence.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
