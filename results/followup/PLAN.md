# Follow-up pre-registration: answer-chunk injection in free text

Status: **written before any run; not approved to run.** Changes after the first real
run go under "Amendments" with date and reason. Prepared 2026-10-23.

## Question

The chunk-choice analyses (`results/SYNTHESIS.md`) found that chunk judges accept when they
receive the partner's answer content as raw-log text (85/170 vs 8/50), but could not
separate the content from its provenance label, the menu or the choice. This follow-up adds
one verbatim answer chunk to the free-text channel, with and without the raw-log label.

- **H1 (primary).** Receiving the partner's answer chunk labelled as verbatim raw log (V)
  raises the judge's individual ACCEPT rate relative to no injection (none).
- **H2 (secondary).** V raises ACCEPT relative to the same chunk labelled as ordinary
  evidence (E), i.e. the provenance label matters beyond the content.

## Design

- **Base:** the free-text arm as run for sequences 6–11 (current harness, working pytest),
  unchanged rule, reward, prompts and model (GPT-6-Luna, reasoning high, temperature 1.0,
  full cross-episode memory, raw-only policy, shared verdict-accuracy reward). Config:
  `configs/followup_answer_injection.yaml`.
- **Sequences:** 1–11 (option a), or 1–15 / 1–20 (option b), 10 episodes each, all on the
  current harness (sequences 1–5 were previously run on the older harness).
- **Unit:** judge-episode (each agent's verdict on its partner); 20 per sequence.
- **Assignment:** each judge-episode independently to none / V / E, 1/3 each, by
  `sha256(seed | manifest stem | episode index | judge) mod 3`, seed **20261023**
  (`experiments/answer_injection.py:assign_condition`). The full table is pre-generated in
  `assignments.csv`: sequences 1–11 give none 70, V 79, E 71; 1–15 give 97 / 108 / 95;
  1–20 give 128 / 138 / 134. Balance across episodes and sequences: chi-square p = 0.83 / 0.94 (11 sequences), 0.69 / 0.98 (15), 0.82 / 0.87 (20).
- **Manipulation** (`experiments/answer_injection.py`, hooked before round 1 in
  `experiments/episode_runner.py`):
  - The chunk is the 200-character slice of the partner's serialized raw log
    (`messaging.raw_log_chunks`) that contains the value of the partner's last
    `save_final_answer` `answer` argument. If no single chunk holds the whole value, the
    first chunk containing part of it is used and `fallback_first_partial_chunk` is logged.
    If the partner saved no answer, nothing is delivered (`delivered: false`).
  - **V:** delivered to the judge from the partner as `[type=raw_log_chunk]`, followed by a
    runner notice: "Before round 1, the runner delivered one extra message from Bob: chunk k
    of Bob's raw log, delivered verbatim. It does not count toward Bob's messages."
  - **E:** the same chunk as `[type=evidence]`, notice: "Before round 1, the runner
    delivered one extra message from Bob: an evidence message. It does not count toward
    Bob's messages." (No "verbatim" or "raw log".)
  - **The sender is told** at its next turn, with the chunk text: "Before round 1, the
    runner delivered one extra message from you to Alice: chunk k of your raw log, delivered
    verbatim [E: an evidence message]. It does not count toward your messages. Its text: …"
  - V and E share one template: the only differences are the `type` label and the phrase
    "chunk k of X raw log, delivered verbatim" vs "an evidence message" (checked by diff on
    the dry run). With no injection, the system prompts, peer brief, round instructions,
    verdict prompt and message headers are byte-identical to the stored free-text run
    (sequence 8, episode 7).
  - The injection is logged as its own event (`tool: "answer_injection"`), never a
    `send_message`, so it does not use the 5 × 200 budget and does not enter existing
    send counts. Each episode result carries an `answer_injection` record per judge.
- **Verified without a model** (`tests/test_answer_injection.py`, 7 tests; full suite 18
  passed): exact answer span on every stored free-text log of sequences 6–11, labels and
  notices per condition, no budget use (5 sends per agent in all conditions), deterministic
  assignment. Mock dry run: `dry_run.md`.

## Outcomes and analysis

- **Primary outcome:** individual ACCEPT (judge's verdict = accept). Forced verdicts count
  as REJECT (harness default) and are reported.
- **Primary contrast:** V vs none. **Secondary:** V vs E.
- **Model:** `accept ~ condition + episode + n_prior_injections + (1|sequence) +
  (1|sequence:agent)`, Bayesian mixed logistic (statsmodels `BinomialBayesMixedGLM`, VB, as
  in `analysis/chunk_rerun/robustness.py`). `condition` reference = none; the V − E contrast
  is read from a refit with reference E. `n_prior_injections` = number of this judge's
  earlier episodes in the sequence with a delivered V or E injection. Report log-odds,
  odds ratio and 95% CI; H1 is supported if the V interval excludes 0 in the positive
  direction. Also report raw counts per condition and a sequence-level bootstrap (10,000
  draws) of the V − none difference in ACCEPT rate.
- **Analysis set:** intention-to-treat by assigned condition. Sensitivity: delivered only;
  excluding `fallback_first_partial_chunk` cases.
- **Manipulation checks** (keyword coding, no model calls; definitions fixed now):
  1. *References the injected content:* the judge's verdict reasoning contains a ≥ 20
     character run of the injected chunk (whitespace-normalized, JSON escapes decoded), or
     mentions "chunk", "raw-log chunk", "extra message", "runner delivered" or "verbatim".
     For none, the same test is applied to the chunk that would have been injected, giving
     the base rate.
  2. *Still invokes the policy:* the step-3 policy pattern (`\bpolic(y|ies)\b`, "verdict
     rule/basis/requirement", "must be based", complete-raw-log requirement) in the verdict
     reasoning, and the strict pattern `\bpolic(y|ies)\b|\bverdict (rule|basis|requirement)`
     in the judge's own messages, by condition.
- **Secondary and exploratory:** joint ACCEPT by the pair's condition combination; ACCEPT by
  task type × condition; verdict accuracy by condition; partner's condition as a covariate
  (reciprocity); whether senders mention the injection in later messages.
- **No interim looks.** One run per approved size; no stopping on results.

## Known limitations (decided, not fixed)

- **Data-search answers never fit one chunk.** In stored free-text logs the answer value
  fits inside one 200-character chunk for 75/78 code-analysis, 19/64 record-extraction and
  0/78 data-search verdicts (median value 5, 156 and 484 characters). Data-search
  injections therefore carry only the first part of the ID list.
- **The chunk is raw JSON in both V and E** and may include the tail of the partner's
  written reasoning (the dry run's chunk ends "…Therefore the implementation has a
  bug.","answer":"bug"}…"). E changes the label and description, not the look; V vs E
  tests the label, and judges may still infer provenance in E.
- **Interference.** Injections shape cross-episode memory and the partner's behaviour;
  `n_prior_injections` adjusts for the judge's own history only.
- One model; sample sizes below.

## Cost (from stored usage; actual billed amounts)

Free-text runs on the current harness (sequences 6–11, 6 runs) cost **$0.377 per sequence**
(range $0.320–$0.426; 9.1M input tokens, 44k output tokens, 263 calls per run). The
injection adds about 400 characters per injected judge-episode, negligible against 9.1M.

| Sequences | Expected | Range (min–max per sequence) | With 15% margin |
|---|---|---|---|
| 11 | $4.15 | $3.52–$4.69 | $4.77 |
| 15 | $5.66 | $4.80–$6.39 | $6.51 |
| 20 | $7.54 | $6.40–$8.52 | $8.67 |

No LLM judges are planned; manipulation checks are keyword-coded.

## Power (V vs none; `power.json`, `analysis/followup/power.py`)

Simulated 1,000 datasets per cell from a logistic model calibrated to the existing free-text
runs (sequence SD 0.2, agent SD 0.9, episode slope 0.25 log-odds, none = 27% on average),
analysed with logistic GEE (groups = sequence:agent, robust SE), two-sided alpha 0.05.
The plain two-proportion z-test is shown for comparison. Judge-episodes per condition are
about 73 / 100 / 133 (actual assignment: V 79 / 108 / 138, none 70 / 97 / 128).

| Sequences | V = 45% (+1.00 log-odds) | V = 50% (+1.26 log-odds) | z-test, 45% / 50% | Cost (expected) |
|---|---|---|---|---|
| 11 | **0.69** | **0.88** | 0.64 / 0.84 | $4.15 |
| 15 | **0.84** | **0.96** | 0.77 / 0.93 | $5.66 |
| 20 | **0.92** | **0.99** | 0.88 / 0.98 | $7.54 |

For 80% power on V vs none: 11 sequences suffice only if V ≈ 50%; 15 sequences cover
V ≈ 45%. V vs E (secondary) is underpowered at every size unless the label effect is about
as large as the V vs none effect.

## Amendments

(none)
