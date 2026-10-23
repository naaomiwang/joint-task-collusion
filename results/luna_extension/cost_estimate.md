# Cost estimate: Luna extension (33 new runs)

Per-sequence billed cost of the current-harness runs (sequences 6–11, 6 runs per arm):
free text $0.377 ($0.320–$0.426), chunks $0.807 ($0.716–$0.884).
Verbatim has no runs yet; it is priced as free text × 1.25 (rejected excerpts add retry calls), range ×1.0–×1.5.

| Runs | Expected | Range |
|---|---|---|
| Free text, 9 sequences (1–5, 12–15) | $3.39 | $2.88–$3.83 |
| Chunks, 9 sequences (1–5, 12–15) | $7.26 | $6.44–$7.96 |
| Verbatim, 15 sequences (1–15) | $7.07 | $4.80–$9.59 |
| **Total** | **$17.72** | **$14.12–$21.38** |

Hard cap $24 (all attempts). No LLM judges. Prices: OpenRouter list for openai/gpt-6-luna,
$0.10 / $0.01 cached / $0.50 per 1M tokens (unchanged since the 6–11 runs).
