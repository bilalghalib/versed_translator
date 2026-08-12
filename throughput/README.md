# throughput/

Modal serving layer for TranslateGemma 27B/12B — vLLM batch inference on
H100. Roadmap: C2 checkpoint 3 (harness adapter), reused as C3's serving
path for the measured-economics grid.

**⚠️ WARNING: every command below spins real, paid Modal GPU/CPU time.**
None of them were run to produce this README — the numbers under "expected
costs" are back-of-envelope estimates from the price constant in
`serve_translategemma.py` (`H100_LIST_PRICE_PER_HOUR_USD`, marked
NEEDS-VERIFICATION there), not measurements. Confirm current Modal pricing
before trusting any $ figure here. C3 is where real saturated-throughput
numbers get measured and this file's estimates get replaced.

Rights hygiene: this directory holds only code + this README. No Arabic or
English source text lives here or gets written here — `run_batch` reads
input jsonl and writes output jsonl exclusively under
`/Volumes/Nodes/versed-translator/{benchmark-data,runs}/`, never inside the
repo. `results/` in this directory stays empty (aggregate stats/reports
without quoted passages may go here later, per repo HARD RULES).

## Files

- `serve_translategemma.py` — the Modal app (`versed-tg-serve`):
  - `download_weights` — CPU function, snapshots a TranslateGemma repo into
    the `versed-model-weights` volume, idempotent, revision-pinned (records
    the resolved HF commit SHA to `weights_manifest.json` on the volume).
  - `check_weights_present` — cheap CPU healthcheck, no GPU spend.
  - `TranslateGemmaServer` — GPU (H100) class, loads one model into a vLLM
    engine (BF16, `max_model_len=4096`) and answers batched
    `translate_batch` calls using vLLM's native batching (all prompts in
    one `llm.generate(...)` call, not a per-item loop). Scale-to-zero
    (`min_containers=0`), short idle timeout (`scaledown_window=180s`).
  - `smoke` (local_entrypoint) — CPU healthcheck, then a real 2-line GPU
    translate call end to end; prints results + a rough $ estimate.
  - `run_batch` (local_entrypoint) — reads a jsonl of `{id, arabic}`,
    chunks it, calls the GPU server, writes results jsonl incrementally
    (so a mid-run failure doesn't lose completed chunks) plus a
    `_run_summary` trailer line with cost/timing.
- `results/` — empty for now; reserved for C3 throughput-grid outputs
  (aggregate stats/JSON only, never quoted source/translation text).

## Prerequisites

- A Modal secret named `huggingface` with key `HF_TOKEN` (do not create or
  read this secret from agent code — assumed to already exist).
- HF license accepted (once, account `bilalghalib`) on the
  `google/translategemma-27b-it` and `-12b-it` model pages.
- `modal` CLI available (`~/mambaforge/bin/modal`, or `uv run modal`).

## Exact commands

### (a) Prefetch weights (CPU only, no GPU spend; still costs network/disk
time and counts against Modal CPU-minute billing)

```bash
uv run modal run throughput/serve_translategemma.py::download_weights --model-key 27b
uv run modal run throughput/serve_translategemma.py::download_weights --model-key 12b
```

Idempotent — re-running with the same `--model-key` after weights are
present is a no-op (checked via `weights_manifest.json` on the volume).
Pass `--force true` to re-snapshot. Expected cost: CPU-only, dominated by
~50-60GB (27B) / ~25GB (12B) network transfer; call it low single-digit
dollars of Modal CPU-minute billing, not GPU.

### (b) Smoke test (spins one H100 container)

```bash
uv run modal run throughput/serve_translategemma.py::smoke --model-key 27b
```

Aborts before touching the GPU if weights aren't present yet. If present:
boots one H100 container (cold start likely 2-5 min for a 27B BF16 load),
translates the 2 hardcoded public-domain lines, prints results + metadata
+ a rough cost estimate, then the container scales down after
`SCALEDOWN_WINDOW_SECONDS` (180s) of idleness.

Expected cost (rough, NEEDS-VERIFICATION price constant): cold start
(~3 min) + inference (~seconds) + idle-down (~3 min) ≈ 6-7 H100-minutes ≈
**$0.40-$0.45** at the placeholder $3.95/H100-hr.

### (c) Batch run from a jsonl

Input format: one `{"id": ..., "arabic": ...}` per line. Output format: one
result per line (`{"id", "english", "output_tokens", "latency_s"}` or
`{"id", "english": null, "error"}` for a skipped/failed item), plus a
trailing `{"_run_summary": {...}}` line.

```bash
uv run modal run throughput/serve_translategemma.py::run_batch \
  --input  /Volumes/Nodes/versed-translator/benchmark-data/v0.1/some_subset.jsonl \
  --output /Volumes/Nodes/versed-translator/runs/translategemma-27b/some_subset.jsonl \
  --model-key 27b \
  --chunk-size 128 \
  --temperature 0.1 \
  --max-new-tokens 1024
```

Expected cost scales with total items and prompt/output length; this
script does not itself estimate a whole-run cost ahead of time (that is
C3's job, once saturated throughput is actually measured — the
hypothetical 22k tok/s figure mentioned in planning docs is explicitly
unconfirmed). For a rough per-item ceiling: at ~1-2s/item on a warm
container with modest batch sizes, 1,000 items is on the order of
**15-35 H100-minutes ≈ $1-2.5** — treat this as a placeholder to be
replaced by C3 measurements, not a budget commitment.

## Config choices (recorded for D3a)

- **vLLM version pin:** `0.11.0` (see `VLLM_VERSION` in
  `serve_translategemma.py`) — NEEDS-VERIFICATION before the first real
  `run_batch`: confirm this version is current and actually supports
  TranslateGemma's architecture; bump deliberately if not, and note why.
- **Base image:** `nvidia/cuda:12.4.1-devel-ubuntu22.04` + Python 3.11.
- **GPU:** H100 (single), BF16, `max_model_len=4096`,
  `gpu_memory_utilization=0.90`.
- **Sampling defaults:** `temperature=0.1`, `top_p=1.0`,
  `max_new_tokens=1024`.
- **Cost controls:** `min_containers=0` (scale to zero),
  `scaledown_window=180s`, generous per-call `timeout` (1hr) and
  `startup_timeout` (15min) so a slow cold-start or a large batch doesn't
  get killed mid-run.

## Not implemented here (by design)

An OpenAI-compatible web endpoint (`@app.function` + `@modal.asgi_app` or
vLLM's own OpenAI server entrypoint, wrapped behind Modal's web endpoint
decorator) would let the harness (C2) or the VPS worker (C10) call this
over plain HTTP instead of the Modal Python client. Sketch only, not built:
a second `@app.function(gpu="H100", ...)` exposing
`vllm.entrypoints.openai.api_server` via `@modal.web_server(port=8000)`,
sharing the same volume/image/manifest plumbing above. Batch
(`translate_batch`) is the bakeoff path for C2/C3; the web endpoint is a
later convenience layer, not required for measuring throughput or running
the bakeoff.
