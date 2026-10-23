# Cost estimates and ceiling risk for extension runs

Script: `analysis/paper_metrics/cost_and_ceiling.py` → `cost_and_ceiling.json`. No model calls.
Prices: OpenRouter `/api/v1/models`, fetched 2026-10-23 (USD per 1M tokens: input / cached
input / output).

| Model | Input | Cached | Output |
|---|---|---|---|
| DeepSeek V4.1 Flash | 0.30 | 0.006 | 1.20 |
| Gemini-3.1-Flash-Lite | 0.25 | 0.025 | 1.50 |
| GPT-6-Luna | 0.10 | 0.01 | 0.50 |

A sequence is 10 episodes with both agents; one arm = free text or chunk-choice. All runs
use the current harness and `task/task_sequences_25x10` manifests. No LLM judges included.

## Per-sequence cost, by source

| | Free text | Chunk-choice | Source |
|---|---|---|---|
| GPT-6-Luna | $0.377 ($0.320–$0.426) | $0.807 ($0.716–$0.884) | billed, 6 runs each (sequences 6–11) |
| DeepSeek, billed (cheap pinned providers) | $0.549 | $1.16 | billed; chunk run stopped at 5 episodes ($0.335) and is scaled by the share of cost in episodes 1–5 of full Luna chunk runs (29%) |
| DeepSeek, list price | $1.18 | $2.57 | same tokens at list price |
| Gemini, cached, Luna token profile | $0.81 | $1.66 | Luna tokens at Gemini prices |
| Gemini, cached, DeepSeek token profile | $1.33 | $2.87 | DeepSeek tokens at Gemini prices |
| Gemini, no caching (upper bound) | $2.34–$4.34 | $2.16–$8.17 | both profiles |

DeepSeek used about 1.8× Luna's input tokens per free-text sequence (16.4M vs 9.1M), so the
DeepSeek profile is the cautious one. Gemini has no runs here, and its reasoning length is
unknown, so the Gemini rows are a bracket rather than an estimate; a 1-sequence Gemini
screening run (≈ $1–$3) would pin it down.

## Scenarios

| Scenario | Estimate |
|---|---|
| (a) DeepSeek, both arms × 15 sequences | **$25.7** at the pinned providers used before; $56.3 at list price |
| (a) Gemini Flash-Lite, both arms × 15 sequences | **$37** (Luna profile, cached) to **$63** (DeepSeek profile, cached); up to $188 without caching |
| (b) Luna sequences 1–5 rerun on the current harness, both arms | **$5.92** ($5.18–$6.55) |
| (c) 4 new Luna sequences, both arms (to reach 15) | **$4.74** ($4.14–$5.24) |

(b) + (c) together: $10.66 ($9.32–$11.79). None of these fit the current $10 follow-up budget
on top of that run.

## Ceiling risk: how quickly fresh agents start accepting

| Data | Fresh-agent behaviour |
|---|---|
| GPT-6-Luna (this study) | 0/44 ACCEPT in episode 1; median first ACCEPT episode 6 (free) / 3 (chunks); joint ACCEPT 9/110 and 29/110 |
| **DeepSeek V4.1 Flash** (1 pair per arm, `results/d`) | Episode 1: 0/2 ACCEPT in both arms; from episode 2 on, both agents accept: joint ACCEPT 9/10 (free) and 4/5 (chunks, 5 episodes); individual 18/20 and 8/10 |
| Qwen 3.7 Flash (`results/rr`, for reference) | Chunks: 4/20 ACCEPT, no joint ACCEPT in 10 episodes; free text stopped after 2 episodes (joint ACCEPT in episode 2) |
| **Gemini-3.1-Flash-Lite** (paper's released controlled-peer cells: fresh judge vs a scripted partner, 50 sequences each) | Episode 1: 0–1/50 ACCEPT. ACCEPT climbs gradually: verbatim raw-prefix cells 68/500 and 82/500 (episode 10: 12/50 and 12/50); summary cells 175/500 and 206/500 (episode 10: 33/50 and 31/50); 27–44 of 50 sequences ever accept |

**Reading.** DeepSeek is at the ceiling by episode 2 in both arms, so a free-text vs chunks
comparison would have almost no room to move EC (9/10 vs 4/5 already); 15 sequences would
mostly measure the single rejecting episode. Gemini Flash-Lite starts slowly and stays well
below the ceiling over 10 episodes, so it has room for an arm effect. It is also the only
model here whose released data compares verbatim and summary evidence, and there verbatim
raw-prefix evidence was accepted *less* than a summary, the opposite direction to the Luna
chunk result (different design: a scripted partner and the first 1,000 characters rather
than chosen chunks). The Sticky Collusion report (Cahyono, 2026) agrees on the ordering:
fresh DeepSeek pairs formed collusion within four episodes in 15/15 runs (individual ACCEPT
79%), against 22% for fresh Gemini pairs and 31% for Luna.
