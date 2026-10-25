"""Pre-registered analysis of the Luna extension (results/luna_extension/PLAN.md), fixed before data.

Reuses analysis/paper_metrics/make_figures.py (EC/U/TC/HC, bootstrap, Wilson, sign test,
Wilcoxon), analysis/chunk_rerun/accept_reasons.py (category 1b), free_text_evidence.py
(can't-send flag, log normalization), coordination_null.py (permutation null) and
released_2x2/informativeness.py (answer-bearing tags). No model calls; raw data read only.

    PYTHONUTF8=1 python analysis/final/run_all.py           # real data -> results/PAPER_RESULTS.md
    PYTHONUTF8=1 python analysis/final/run_all.py --test    # existing data only -> results/luna_extension/test_output/
In --test mode the not-yet-run data is replaced by stand-ins (sequences 1-5: original runs; verbatim:
chunk runs), purely to exercise the code. Its numbers mean nothing.
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for sub in ("analysis/paper_metrics", "analysis/chunk_rerun", "analysis/released_2x2"):
    sys.path.insert(0, str(REPO / sub))
sys.path.insert(0, str(REPO))
import make_figures as MF  # noqa: E402
from accept_reasons import ACCEPT_CATS  # noqa: E402
from coordination_null import permute  # noqa: E402
from free_text_evidence import is_ack, normalized_log  # noqa: E402
from informativeness import RawLog, answer_bearing  # noqa: E402
from experiments.protocol.verbatim import EXCERPT_DELIMITER  # noqa: E402

ARMS = ("free", "chunk", "verbatim")
NAME = {"free": "Free text", "chunk": "Chunks", "verbatim": "Verbatim"}
CONTRASTS = (("chunk", "free"), ("verbatim", "free"), ("verbatim", "chunk"))
SOURCES = {
    "real": {"free": ["results/l/f", "results/x/f"], "chunk": ["results/l/c", "results/x/c"], "verbatim": ["results/x/v"]},
    "test": {"free": ["results/l/f", "results/openai-gpt-6-luna"],
             "chunk": ["results/l/c", "results/chunk_choice/openai-gpt-6-luna"],
             "verbatim": ["results/l/c", "results/chunk_choice/openai-gpt-6-luna"]},
}
SUPPLEMENTARY = {"free": ["results/openai-gpt-6-luna"], "chunk": ["results/chunk_choice/openai-gpt-6-luna"]}
NEW_SEQS = [1, 2, 3, 4, 5, 12, 13, 14, 15]
EXPECTED = "openai/gpt-6-luna"
B, SEED = 4000, 20261023


def load(dirs):
    runs = {}
    for d in dirs:
        for p in glob.glob(str(REPO / d / "**" / "run.json"), recursive=True):
            r = json.load(open(p, encoding="utf-8"))
            if r["run_config"].get("verdict_policy") != "raw-only" or len(r["results"]) != 10:
                continue  # incomplete runs never enter the analysis
            s = int(re.search(r"rep(\d+)_sampled", r["run_config"]["manifest"]).group(1))
            runs.setdefault(s, r)
    return runs


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [0.0] * len(ps), 0.0
    for k, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - k) * ps[i]))
        adj[i] = running
    return adj


def per_seq(runs):
    return {s: {**MF.trajectory_collusion(r),
                "accepts": sum(int(MF.episode_verdicts(e).get(a) == "accept") for e in MF.ordered_episodes(r) for a in ("alice", "bob"))}
            for s, r in runs.items()}


def arm_metrics(rows, seqs, rng):
    r = [rows[s] for s in seqs]
    mut = np.array([x["mutual_accept"] for x in r]); eps = np.array([x["episodes"] for x in r]); acc = np.array([x["accepts"] for x in r])
    tc, hc = sum(x["collusive"] for x in r), sum(x["converged"] for x in r)
    return {"EC": {"k": int(mut.sum()), "n": int(eps.sum()), "rate": mut.sum() / eps.sum(), "ci": MF.boot_ratio(mut, eps, rng)},
            "U": {"k": int(acc.sum()), "n": int(2 * eps.sum()), "rate": acc.sum() / (2 * eps.sum()), "ci": MF.boot_ratio(acc, 2 * eps, rng)},
            "TC": {"k": tc, "n": len(r), "rate": tc / len(r), "ci": MF.wilson(tc, len(r))},
            "HC": {"k": hc, "n": len(r), "rate": hc / len(r), "ci": MF.wilson(hc, len(r))}}


def paired(rows_a, rows_b, seqs, key, den, rng):
    d = np.array([rows_a[s][key] - rows_b[s][key] for s in seqs], dtype=float)
    out = {"n": len(seqs), "sign": MF.sign_test(d), "wilcoxon_p": MF.wilcox(d)}
    if den:
        idx = rng.integers(0, len(d), size=(B, len(d)))
        out["mean_diff"] = float((d / den).mean())
        out["ci"] = [float(np.percentile((d[idx] / den).mean(axis=1), q)) for q in (2.5, 97.5)]
    return out


def model_ids(runs):
    ids = set()
    for r in runs.values():
        for e in r["results"]:
            for u in e.get("llm_usage", []):
                if u.get("response_status", "accepted") == "accepted":  # failed attempts carry no model
                    ids.add(u.get("response_model"))
    return ids


def verbatim_mechanics(runs):
    att = rej = skipped = rounds = delivered = excerpts = 0
    for r in runs.values():
        for e in r["results"]:
            sends = [x for x in e["events"] if x.get("tool") == "send_message"]
            att += len(sends); rej += sum(1 for x in sends if x.get("verbatim_rejection"))
            ok = [x for x in sends if x.get("success")]
            delivered += len(ok); excerpts += sum(x.get("excerpt_count", 1) for x in ok)
            for a in ("alice", "bob"):
                for k in range(5):
                    rounds += 1
                    skipped += not any(x.get("success") and x.get("actor") == a and x.get("round") == k for x in sends)
    return {"rejected_of_attempts": f"{rej}/{att}", "skipped_rounds": f"{skipped}/{rounds}",
            "excerpts_per_delivered_message": round(excerpts / delivered, 2) if delivered else None}


def received_answer(e, judge, arm):
    sender = "bob" if judge == "alice" else "alice"
    raw = RawLog(e["agents"][sender]["private_raw_log"])
    tags = set()
    for x in e["events"]:
        if x.get("tool") != "send_message" or not x.get("success") or x.get("actor") != sender:
            continue
        if arm == "chunk":
            lim = 200
            st = raw.locate(x["content"], (int(x.get("chunk_id", 1)) - 1) * lim)
            if st is not None:
                tags |= raw.tags_for(st, st + len(x["content"]))
        else:
            norm, pos = normalized_log(raw.text)
            for ex in x["content"].split(EXCERPT_DELIMITER):
                ex = re.sub(r"\s+", " ", ex).strip()
                i = norm.find(ex) if ex else -1
                if i >= 0:
                    tags |= raw.tags_for(pos[i], pos[i + len(ex) - 1] + 1)
    return answer_bearing(tags)


def excerpts_located(runs, seqs):
    tot = found = 0
    for s in seqs:
        for e in MF.ordered_episodes(runs[s]):
            for x in e["events"]:
                if x.get("tool") == "send_message" and x.get("success"):
                    norm, _ = normalized_log(RawLog(e["agents"][x["actor"]]["private_raw_log"]).text)
                    for ex in x["content"].split(EXCERPT_DELIMITER):
                        ex = re.sub(r"\s+", " ", ex).strip()
                        tot += 1; found += bool(ex) and ex in norm
    return f"{found}/{tot}"


def exploratory(runs_by_arm, seqs, rng):
    X = {}
    # (a) ACCEPT with vs without the partner's answer content, chunk and verbatim arms.
    X["a_accept_by_answer_content"] = {}
    X["a_excerpts_located"] = excerpts_located(runs_by_arm["verbatim"], seqs)
    for arm in ("chunk", "verbatim"):
        cnt = {True: [0, 0], False: [0, 0]}
        for s in seqs:
            for e in MF.ordered_episodes(runs_by_arm[arm][s]):
                for j in ("alice", "bob"):
                    k = bool(received_answer(e, j, arm))
                    cnt[k][0] += int(MF.episode_verdicts(e).get(j) == "accept"); cnt[k][1] += 1
        X["a_accept_by_answer_content"][arm] = {"with": f"{cnt[True][0]}/{cnt[True][1]}", "without": f"{cnt[False][0]}/{cnt[False][1]}"}
    pat = ACCEPT_CATS["c1b_incomplete"]
    X["b_incomplete_in_accept_reasons"] = {}
    X["d_accept_on_incorrect_work"] = {}
    for arm in ARMS:
        k = n = ki = ni = 0
        for s in seqs:
            for e in MF.ordered_episodes(runs_by_arm[arm][s]):
                for j in ("alice", "bob"):
                    peer = "bob" if j == "alice" else "alice"
                    acc = MF.episode_verdicts(e).get(j) == "accept"
                    if acc:
                        n += 1; k += bool(pat.search((e["agents"][j].get("verdict_submission") or {}).get("reasoning", "")))
                    if e["agents"][peer].get("expected_verdict") == "fail":
                        ni += 1; ki += int(acc)
        X["b_incomplete_in_accept_reasons"][arm] = f"{k}/{n}"
        X["d_accept_on_incorrect_work"][arm] = f"{ki}/{ni}"
    k = n = 0
    for s in seqs:
        for e in MF.ordered_episodes(runs_by_arm["free"][s]):
            n += 1; k += any(is_ack(m["content"]) for m in e.get("channel_transcript", []))
    X["c_free_episodes_cant_send"] = f"{k}/{n}"
    X["e_coordination_null_within_episode"] = {}
    for arm in ARMS:
        a = np.array([[int(MF.episode_verdicts(e).get("alice") == "accept") for e in MF.ordered_episodes(runs_by_arm[arm][s])] for s in seqs])
        b = np.array([[int(MF.episode_verdicts(e).get("bob") == "accept") for e in MF.ordered_episodes(runs_by_arm[arm][s])] for s in seqs])
        null = permute(a, b, None, np.random.default_rng(SEED), "primary")
        obs = int((a * b).sum())
        X["e_coordination_null_within_episode"][arm] = {"observed": obs, "null_mean": float(null.mean()),
                                                        "null_95": [float(np.percentile(null, 2.5)), float(np.percentile(null, 97.5))],
                                                        "p_one_sided": float((np.sum(null >= obs) + 1) / (len(null) + 1))}
    return X


def slope_models(runs_by_arm, seqs):
    import pandas as pd
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    out = {}
    for hi, lo in CONTRASTS:
        rows = []
        for arm in (hi, lo):
            for s in seqs:
                for e in MF.ordered_episodes(runs_by_arm[arm][s]):
                    v = MF.episode_verdicts(e)
                    for a in ("alice", "bob"):
                        rows.append({"seq": s, "sa": f"{s}_{a}", "arm": int(arm == hi), "episode": e["episode_index"] + 1,
                                     "accept": int(v.get(a) == "accept")})
        df = pd.DataFrame(rows)
        m = BinomialBayesMixedGLM.from_formula("accept ~ arm + episode",
                                               {"seq": "0 + C(seq)", "seq_arm": "0 + C(seq):arm", "sa": "0 + C(sa)"}, df)
        r = m.fit_vb(); i = m.exog_names.index("arm"); mu, sd = float(r.fe_mean[i]), float(r.fe_sd[i])
        out[f"{hi}_vs_{lo}"] = {"logodds": mu, "ci": [mu - 1.96 * sd, mu + 1.96 * sd], "odds_ratio": float(np.exp(mu))}
    return out


def pct(x):
    return f"{100 * x:.0f}%"


def report(R, test):
    L = [("# TEST RUN on existing data with stand-ins — numbers are meaningless\n" if test else "") +
         "# Luna extension: results", "", f"Generated by `analysis/final/run_all.py`{' --test' if test else ''}. "
         "Pre-registration: `results/luna_extension/PLAN.md`.", "", "## Pre-registered", "",
         f"Primary set: {len(R['seqs'])} sequences ({', '.join(map(str, R['seqs']))}), 10 episodes per arm.", "",
         "### Primary: EC (episodes where both agents ACCEPT)", "",
         "| Arm | EC [95% CI] |", "|---|---|"]
    for arm in ARMS:
        x = R["metrics"][arm]["EC"]; L.append(f"| {NAME[arm]} | {x['k']}/{x['n']} = {pct(x['rate'])} [{pct(x['ci'][0])}, {pct(x['ci'][1])}] |")
    L += ["", "| Contrast | Mean diff [95% CI] | Sign test (up/down/tied) | p | Holm p | Wilcoxon p | Holm p |", "|---|---|---|---|---|---|---|"]
    for c, x in R["primary"].items():
        st = x["sign"]
        w = "n/a" if x["wilcoxon_p"] is None else f"{x['wilcoxon_p']:.4f}"
        wh = "n/a" if x["wilcoxon_holm"] is None else f"{x['wilcoxon_holm']:.4f}"
        L.append(f"| {c} | {100 * x['mean_diff']:+.1f} pts [{100 * x['ci'][0]:+.1f}, {100 * x['ci'][1]:+.1f}] | "
                 f"{st['up']}/{st['down']}/{st['tied']} | {st['p']:.4f} | {x['sign_holm']:.4f} | {w} | {wh} |")
    L += ["", "### Secondary", "", "| Metric | " + " | ".join(NAME[a] for a in ARMS) + " |", "|---|---|---|---|"]
    for m in ("U", "TC", "HC"):
        L.append(f"| {m} | " + " | ".join(
            f"{R['metrics'][a][m]['k']}/{R['metrics'][a][m]['n']} = {pct(R['metrics'][a][m]['rate'])} "
            f"[{pct(R['metrics'][a][m]['ci'][0])}, {pct(R['metrics'][a][m]['ci'][1])}]" for a in ARMS) + " |")
    L += ["", "| Contrast | Metric | Sign test (up/down/tied), p | Wilcoxon p |", "|---|---|---|---|"]
    for c, d in R["secondary_paired"].items():
        for m, x in d.items():
            w = "n/a" if x["wilcoxon_p"] is None else f"{x['wilcoxon_p']:.4f}"
            L.append(f"| {c} | {m} | {x['sign']['up']}/{x['sign']['down']}/{x['sign']['tied']}, p = {x['sign']['p']:.4f} | {w} |")
    L += ["", "U with a random arm slope by sequence (log-odds [95% CI], odds ratio):", ""]
    for c, x in R["slope_models"].items():
        L.append(f"- {c.replace('_vs_', ' vs ')}: {x['logodds']:+.2f} [{x['ci'][0]:+.2f}, {x['ci'][1]:+.2f}], OR {x['odds_ratio']:.2f}")
    L.append("")
    L.append("(Variational Bayes; these intervals tend to be narrower than the sequence-level tests above.)")
    rp = R["replication"]
    rw = "n/a" if rp["wilcoxon_p"] is None else f"p = {rp['wilcoxon_p']:.4f}"
    L += ["", f"Replication, chunks vs free on newly run sequences (n = {rp['n']}): sign test "
          f"{rp['sign']['up']}/{rp['sign']['down']}/{rp['sign']['tied']}, p = {rp['sign']['p']:.4f}; Wilcoxon {rw}.",
          "", "Verbatim mechanics: rejected sends " + R["verbatim_mechanics"]["rejected_of_attempts"]
          + " of attempts; skipped rounds " + R["verbatim_mechanics"]["skipped_rounds"]
          + f"; {R['verbatim_mechanics']['excerpts_per_delivered_message']} excerpts per delivered message.", "",
          f"Model identifier: {', '.join(sorted({m for v in R['model_ids'].values() for m in v}, key=str))} in every run."
          + ("" if R["ids_ok"] else " **Differs between runs; old vs new reported below.**"), "",
          f"Supplementary, EC in the original runs of sequences 1–5: {R['supplementary']}", "",
          "## Exploratory", ""]
    X = R["exploratory"]
    a = X["a_accept_by_answer_content"]
    L += ["(a) ACCEPT with vs without the partner's answer content received "
          f"({X['a_excerpts_located']} verbatim excerpts located in the sender's log):", "",
          "| Arm | With answer content | Without |", "|---|---|---|"]
    L += [f"| {NAME[arm]} | {a[arm]['with']} | {a[arm]['without']} |" for arm in ("chunk", "verbatim")]
    L += ["", "| | " + " | ".join(NAME[x] for x in ARMS) + " |", "|---|---|---|---|",
          "| (b) ACCEPT reasons mentioning missing or incomplete evidence | "
          + " | ".join(X["b_incomplete_in_accept_reasons"][x] for x in ARMS) + " |",
          "| (d) ACCEPT on incorrect work | " + " | ".join(X["d_accept_on_incorrect_work"][x] for x in ARMS) + " |",
          "", f"(c) Free-text episodes where an agent says the log can't be sent: {X['c_free_episodes_cant_send']}.", "",
          "(e) Joint ACCEPTs vs a null shuffling Bob's verdicts across sequences within each episode index "
          "(10,000 permutations, one-sided p):", "", "| Arm | Observed | Null mean [95%] | p |", "|---|---|---|---|"]
    for arm in ARMS:
        e = X["e_coordination_null_within_episode"][arm]
        L.append(f"| {NAME[arm]} | {e['observed']} | {e['null_mean']:.1f} [{e['null_95'][0]:.0f}, {e['null_95'][1]:.0f}] | {e['p_one_sided']:.3f} |")
    if not R["ids_ok"]:
        L += ["", "## Old vs new runs (model identifier differs)", "", json.dumps(R["old_vs_new"], indent=1)]
    return "\n".join(L)


def figure(R, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"free": "#6A4FE0", "chunk": "#E8774F", "verbatim": "#1baf7a"}
    fig, ax = plt.subplots(figsize=(7, 3), dpi=160)
    for i, arm in enumerate(ARMS):
        x = R["metrics"][arm]["EC"]
        ax.plot(x["ci"], [i, i], color=col[arm], lw=2)
        ax.plot(x["rate"], i, "o", ms=8, color=col[arm], mec="white", mew=2)
        ax.annotate(f"{x['k']}/{x['n']}", (x["ci"][1], i), xytext=(6, -3), textcoords="offset points", fontsize=9)
    ax.set_yticks(range(3)); ax.set_yticklabels([NAME[a] for a in ARMS]); ax.invert_yaxis()
    ax.set_xlim(0, 1); ax.set_xlabel("EC: episodes with both ACCEPT (95% CI)")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(out / "fig_ec_by_arm.png", facecolor="white"); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--test", action="store_true"); a = ap.parse_args()
    src = SOURCES["test" if a.test else "real"]
    out_dir = REPO / ("results/luna_extension/test_output" if a.test else "results")
    fig_dir = REPO / ("results/luna_extension/test_output" if a.test else "results/luna_extension/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)
    runs = {arm: load(src[arm]) for arm in ARMS}
    seqs = sorted(set.intersection(*(set(runs[arm]) for arm in ARMS)) & set(range(1, 16)))
    missing = {arm: sorted(set(range(1, 16)) - set(runs[arm])) for arm in ARMS}
    rows = {arm: per_seq(runs[arm]) for arm in ARMS}
    rng = np.random.default_rng(SEED)
    R = {"seqs": seqs, "missing": missing, "metrics": {arm: arm_metrics(rows[arm], seqs, rng) for arm in ARMS}}
    R["primary"] = {f"{h} vs {l}": paired(rows[h], rows[l], seqs, "mutual_accept", 10, rng) for h, l in CONTRASTS}
    sh = holm([x["sign"]["p"] for x in R["primary"].values()])
    wp = [x["wilcoxon_p"] for x in R["primary"].values()]
    wh = holm([p if p is not None else 1.0 for p in wp])
    for (k, x), s1, w1, raw in zip(R["primary"].items(), sh, wh, wp):
        x["sign_holm"], x["wilcoxon_holm"] = s1, (w1 if raw is not None else None)
    R["secondary_paired"] = {f"{h} vs {l}": {m: paired(rows[h], rows[l], seqs, key, 0, rng) for m, key in
                                              (("U", "accepts"), ("TC", "collusive"), ("HC", "converged"))} for h, l in CONTRASTS}
    R["slope_models"] = slope_models(runs, seqs)
    new = [s for s in NEW_SEQS if s in seqs]
    R["replication"] = paired(rows["chunk"], rows["free"], new, "mutual_accept", 10, rng)
    R["verbatim_mechanics"] = verbatim_mechanics({s: runs["verbatim"][s] for s in seqs})
    R["model_ids"] = {arm: model_ids({s: runs[arm][s] for s in seqs}) for arm in ARMS}
    R["ids_ok"] = all(set(v) <= {EXPECTED} for v in R["model_ids"].values())
    if not R["ids_ok"]:
        old = [s for s in seqs if 6 <= s <= 11]
        R["old_vs_new"] = {grp: {arm: arm_metrics(rows[arm], g, rng)["EC"] for arm in ARMS} for grp, g in (("6-11", old), ("new", new)) if g}
    sup = {arm: per_seq(load(d)) for arm, d in SUPPLEMENTARY.items()}
    R["supplementary"] = ", ".join(f"{NAME[arm]} {sum(sup[arm][s]['mutual_accept'] for s in sup[arm] if s <= 5)}/"
                                   f"{sum(sup[arm][s]['episodes'] for s in sup[arm] if s <= 5)}" for arm in sup)
    R["exploratory"] = exploratory(runs, seqs, rng)
    R["model_ids"] = {k: sorted(v, key=str) for k, v in R["model_ids"].items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    (fig_dir / "results.json").write_text(json.dumps(R, indent=1, default=str), encoding="utf-8")
    (out_dir / "PAPER_RESULTS.md").write_text(report(R, a.test), encoding="utf-8")
    figure(R, fig_dir)
    print(report(R, a.test))
    return 0


if __name__ == "__main__":
    sys.exit(main())
