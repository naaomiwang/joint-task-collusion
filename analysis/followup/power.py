"""Power for the follow-up's primary contrast (V vs none), by simulation. No model calls.

Data-generating model, calibrated to the existing free-text runs (results/robustness):
logit P(accept) = b0 + 0.25*(episode - 5.5) + u_seq + u_agent + delta*[V] + delta_E*[E],
u_seq ~ N(0, 0.2^2), u_agent ~ N(0, 0.9^2) (one per sequence:agent), episodes 1-10,
2 judges per episode, condition drawn independently 1/3 each per judge-episode.
b0 is set so P(accept | none) averages 27%; delta so P(accept | V) averages the target.
Episode 1 is kept (all 44 existing episode-1 verdicts were REJECT; the trend term covers it).

Analysis per simulated dataset: logistic GEE, groups = sequence:agent, exchangeable,
robust SE, accept ~ condition + episode; two-sided alpha = 0.05 on the V term.
(The pre-registered mixed model is too slow to refit thousands of times; GEE with robust
SE targets the same contrast.) Also reports the simple two-proportion z-test.

    PYTHONUTF8=1 python analysis/followup/power.py
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import norm

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parents[2] / "results" / "followup"
SD_SEQ, SD_AGENT, B_EP, SIMS, SEED = 0.2, 0.9, 0.25, 1000, 20261023


def marginal(b0, delta, rng, n=200_000):
    u = rng.normal(0, SD_SEQ, n) + rng.normal(0, SD_AGENT, n)
    ep = rng.integers(1, 11, n)
    return float(np.mean(1 / (1 + np.exp(-(b0 + B_EP * (ep - 5.5) + u + delta)))))


def solve(target, rng, b0=None):
    lo, hi = -6.0, 6.0
    for _ in range(40):
        mid = (lo + hi) / 2
        p = marginal(mid if b0 is None else b0, 0.0 if b0 is None else mid, rng)
        lo, hi = (mid, hi) if p < target else (lo, mid)
    return (lo + hi) / 2


def simulate(n_seq, b0, dV, dE, rng):
    rows = []
    for s in range(n_seq):
        us = rng.normal(0, SD_SEQ)
        for a in ("alice", "bob"):
            ua = rng.normal(0, SD_AGENT)
            for ep in range(1, 11):
                c = rng.choice(["none", "V", "E"])
                eta = b0 + B_EP * (ep - 5.5) + us + ua + (dV if c == "V" else dE if c == "E" else 0.0)
                rows.append((s, f"{s}_{a}", ep, c, int(rng.random() < 1 / (1 + np.exp(-eta)))))
    return pd.DataFrame(rows, columns=["seq", "sa", "episode", "cond", "accept"])


def power(n_seq, b0, dV, dE, rng):
    hits = fails = 0
    for _ in range(SIMS):
        df = simulate(n_seq, b0, dV, dE, rng)
        try:
            m = smf.gee("accept ~ C(cond, Treatment('none')) + episode", "sa", df,
                        family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
            p = m.pvalues["C(cond, Treatment('none'))[T.V]"]
            hits += int(p < 0.05 and m.params["C(cond, Treatment('none'))[T.V]"] > 0)
        except Exception:
            fails += 1
    return hits / (SIMS - fails), fails


def z_power(p0, p1, n):
    se = np.sqrt(p0 * (1 - p0) / n + p1 * (1 - p1) / n)
    return float(norm.cdf(abs(p1 - p0) / se - norm.ppf(0.975)))


def main() -> int:
    rng = np.random.default_rng(SEED)
    b0 = solve(0.27, rng)
    res = {"b0": b0, "assumptions": {"sd_seq": SD_SEQ, "sd_agent": SD_AGENT, "episode_slope": B_EP,
                                     "none": 0.27, "sims": SIMS}, "rows": []}
    for target in (0.45, 0.50):
        dV = solve(target, rng, b0=b0)
        for n_seq in (11, 15, 20):
            per_arm = round(n_seq * 20 / 3)
            pw, fails = power(n_seq, b0, dV, dV / 2, rng)  # E halfway (irrelevant to V vs none)
            row = {"V_target": target, "delta_V_logodds": dV, "sequences": n_seq,
                   "judge_episodes_per_condition": per_arm, "power_gee": pw, "failed_fits": fails,
                   "power_two_proportion_z": z_power(0.27, target, per_arm)}
            res["rows"].append(row)
            print(row)
    # Secondary V vs E: illustrate with E halfway between none and V.
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "power.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
