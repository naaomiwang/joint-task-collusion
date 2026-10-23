"""Cost estimates for extension runs, and ceiling risk from existing non-Luna data. No model calls.

Cost sources (per sequence = 10 episodes, both agents):
  * GPT-6-Luna: billed cost_usd of the current-harness runs (sequences 6-11), per arm.
  * DeepSeek V4.1 Flash: billed cost_usd of its one free-text run (10 episodes) and one
    chunk-choice run that stopped after 5 episodes; the partial run is extrapolated with the
    share of a full Luna chunk run's cost that falls in episodes 1-5 (memory makes later
    episodes dearer). Those runs were pinned to cheap providers, so the same tokens are also
    repriced at OpenRouter's list price.
  * Gemini-3.1-Flash-Lite: no runs in this repo. Tokens of the Luna and DeepSeek runs are
    repriced at Gemini list prices (two profiles), with and without prompt caching.
Prices (USD per 1M tokens, OpenRouter /api/v1/models, fetched 2026-10-23): see PRICES.

Ceiling risk: how fast fresh agents accept, from results/d (DeepSeek), results/rr (Qwen) and
the paper's released controlled-peer cells (Gemini Flash-Lite judge vs a scripted partner).

    PYTHONUTF8=1 python analysis/paper_metrics/cost_and_ceiling.py
"""

import glob
import json
import statistics as st
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "paper_metrics"
PRICES = {  # input, cached input, output (incl. reasoning)
    "deepseek_list": (0.30, 0.006, 1.20),
    "gemini_list": (0.25, 0.025, 1.50),
    "luna_list": (0.10, 0.01, 0.50),
}


def runs(pattern):
    return [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(str(REPO / pattern), recursive=True))]


def tokens(u):
    return {"uncached": u["input_tokens"] - u["cached_input_tokens"], "cached": u["cached_input_tokens"],
            "out": u["billable_output_tokens"]}


def price(t, p, cache=True):
    inp, cached, out = p
    if not cache:
        return ((t["uncached"] + t["cached"]) * inp + t["out"] * out) / 1e6
    return (t["uncached"] * inp + t["cached"] * cached + t["out"] * out) / 1e6


def first5_share(rs):
    shares = []
    for r in rs:
        per = [e["llm_usage_summary"]["cost_usd"] for e in sorted(r["results"], key=lambda e: e["episode_index"])]
        shares.append(sum(per[:5]) / sum(per))
    return st.mean(shares)


def main() -> int:
    S = {"prices_per_million": PRICES}
    luna = {"free": runs("results/l/f/openai-gpt-6-luna/*/run.json"), "chunk": runs("results/l/c/openai-gpt-6-luna/*/run.json")}
    luna_cost = {a: [r["llm_usage_summary"]["cost_usd"] for r in rs] for a, rs in luna.items()}
    S["luna_per_sequence"] = {a: {"mean": st.mean(v), "min": min(v), "max": max(v), "n": len(v)} for a, v in luna_cost.items()}
    share = first5_share(luna["chunk"])
    ds = {"free": runs("results/d/f/**/run.json")[0], "chunk": runs("results/d/c/**/run.json")[0]}
    ds_tok = {a: tokens(r["llm_usage_summary"]) for a, r in ds.items()}
    ds_tok["chunk"] = {k: v / share for k, v in ds_tok["chunk"].items()}  # extrapolate 5 -> 10 episodes
    S["deepseek_per_sequence"] = {
        "free_billed": ds["free"]["llm_usage_summary"]["cost_usd"],
        "chunk_billed_5_episodes": ds["chunk"]["llm_usage_summary"]["cost_usd"],
        "chunk_billed_extrapolated": ds["chunk"]["llm_usage_summary"]["cost_usd"] / share,
        "episodes_1_5_share_of_cost (Luna chunk runs)": share,
        "free_list_price": price(ds_tok["free"], PRICES["deepseek_list"]),
        "chunk_list_price_extrapolated": price(ds_tok["chunk"], PRICES["deepseek_list"]),
    }
    luna_tok = {a: {k: st.mean(tokens(r["llm_usage_summary"])[k] for r in rs) for k in ("uncached", "cached", "out")}
                for a, rs in luna.items()}
    gem = {}
    for arm in ("free", "chunk"):
        gem[arm] = {
            "luna_tokens_cached": price(luna_tok[arm], PRICES["gemini_list"]),
            "deepseek_tokens_cached": price(ds_tok[arm], PRICES["gemini_list"]),
            "luna_tokens_no_cache": price(luna_tok[arm], PRICES["gemini_list"], cache=False),
            "deepseek_tokens_no_cache": price(ds_tok[arm], PRICES["gemini_list"], cache=False),
        }
    S["gemini_per_sequence"] = gem

    # Scenarios.
    L = S["luna_per_sequence"]
    D = S["deepseek_per_sequence"]
    G = {a: (min(v.values()), st.median(v.values()), max(v.values())) for a, v in gem.items()}
    sc = {
        "a_deepseek_15x2_billed_pinned": 15 * (D["free_billed"] + D["chunk_billed_extrapolated"]),
        "a_deepseek_15x2_list": 15 * (D["free_list_price"] + D["chunk_list_price_extrapolated"]),
        "a_gemini_15x2_low_mid_high": [15 * (G["free"][i] + G["chunk"][i]) for i in range(3)],
        "b_luna_seq1_5_both_arms": {"mean": 5 * (L["free"]["mean"] + L["chunk"]["mean"]),
                                    "min": 5 * (L["free"]["min"] + L["chunk"]["min"]),
                                    "max": 5 * (L["free"]["max"] + L["chunk"]["max"])},
        "c_luna_4_new_both_arms": {"mean": 4 * (L["free"]["mean"] + L["chunk"]["mean"]),
                                   "min": 4 * (L["free"]["min"] + L["chunk"]["min"]),
                                   "max": 4 * (L["free"]["max"] + L["chunk"]["max"])},
    }
    S["scenarios"] = sc

    # Ceiling risk.
    def fresh_stats(r):
        eps = sorted(r["results"], key=lambda e: e["episode_index"])
        v = {a: [int(e["agents"][a]["verdict"] == "accept") for e in eps] for a in ("alice", "bob")}
        mutual = [int(v["alice"][i] and v["bob"][i]) for i in range(len(eps))]
        first = {a: next((i + 1 for i, x in enumerate(v[a]) if x), None) for a in v}
        return {"episodes": len(eps), "accepts": f"{sum(map(sum, v.values()))}/{2 * len(eps)}",
                "episode1_accepts": f"{v['alice'][0] + v['bob'][0]}/2", "first_accept_episode": first,
                "mutual_by_episode": mutual, "first_mutual": next((i + 1 for i, x in enumerate(mutual) if x), None)}
    ceil = {"deepseek_free": fresh_stats(ds["free"]), "deepseek_chunk_5ep": fresh_stats(ds["chunk"])}
    for r in runs("results/rr/**/run.json"):
        ceil[f"qwen3.7_{r['run_config']['comm_mode']}"] = fresh_stats(r)
    ceil["luna_reference"] = {"episode1_accepts": "0/44 (both arms)", "median_first_accept": "6 (free), 3 (chunks)"}
    # Released controlled-peer cells: Gemini Flash-Lite judge (Alice) vs a scripted partner.
    rel = {}
    for f in sorted(glob.glob(str(REPO / "analysis/released_2x2/data/agents__*.parquet"))):
        d = pd.read_parquet(f)
        a = d[(d.agent == "alice") & (~d.is_warmup.fillna(False).astype(bool))]
        cell = Path(f).stem.split("__")[1]
        by_ep = a.groupby("episode_index").verdict.apply(lambda s: f"{(s == 'accept').sum()}/{len(s)}")
        first = a.sort_values("episode_index").groupby("sequence_id").apply(
            lambda g: next((int(e) for e, v in zip(g.episode_index, g.verdict) if v == "accept"), None))
        rel[cell] = {"alice_accept": f"{(a.verdict == 'accept').sum()}/{len(a)}",
                     "by_episode_index": by_ep.to_dict(),
                     "sequences_ever_accepting": f"{int(first.notna().sum())}/{len(first)}",
                     "median_first_accept_index": float(first.dropna().median()) if first.notna().any() else None}
    ceil["gemini_flash_lite_released_controlled_peer"] = rel
    S["ceiling"] = ceil
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_and_ceiling.json").write_text(json.dumps(S, indent=1, default=str), encoding="utf-8")
    print(json.dumps(S, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
