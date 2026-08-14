"""Modal serving layer for TranslateGemma (27B / 12B) — vLLM batch inference.

Roadmap: C2 checkpoint 3 (Modal vLLM/SGLang adapter, also becomes C3's
serving path). See VERSED_TRANSLATION_ROADMAP.md.

This module is code + config only. It never reads or writes Arabic/English
source text inside the repo tree — all real inputs/outputs live under
/Volumes/Nodes/versed-translator/{benchmark-data,runs}/ (see README.md in
this directory). The only Arabic text hardcoded here is the `smoke`
entrypoint's two lines, which are centuries-old public-domain classical
Arabic (not sourced from ATHAR/LK-Hadith/hadith-json), used purely to prove
the serving path works end to end.

Usage (all commands spin real Modal compute — see README.md for costs):

    modal run throughput/serve_translategemma.py::download_weights --model-key 27b
    modal run throughput/serve_translategemma.py::smoke
    modal run throughput/serve_translategemma.py::run_batch --input <jsonl> --output <jsonl>

Design notes:
- One Modal Volume ("versed-model-weights") holds HF snapshots for every
  model key, plus a weights_manifest.json recording the exact revision
  (commit SHA) fetched for each, so re-runs are reproducible and idempotent.
- The GPU-serving class loads a single model per container (selected via a
  modal.parameter) and answers batched translate requests using vLLM's
  native batching: every prompt in a call goes into one llm.generate(...),
  not a Python-level loop of single-item calls.
- Everything scales to zero (min_containers=0) and uses a short
  scaledown_window for cost control; loading a 27B model from the volume is
  itself slow (multi-minute), so "small" here is minutes, not seconds — see
  SCALEDOWN_WINDOW_SECONDS below for the exact tradeoff.
"""

# NOTE: no `from __future__ import annotations` here — modal.parameter() needs
# real (non-stringified) type annotations on @app.cls fields to serialize them.

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import modal

# --------------------------------------------------------------------------
# Constants (needs-verification markers are load-bearing — do not delete)
# --------------------------------------------------------------------------

APP_NAME = "versed-tg-serve"

VOLUME_NAME = "versed-model-weights"
WEIGHTS_MOUNT = "/weights"
MANIFEST_PATH = f"{WEIGHTS_MOUNT}/weights_manifest.json"

HF_SECRET_NAME = "huggingface"  # must already exist in the Modal workspace

MODEL_REPOS: dict[str, str] = {
    "27b": "google/translategemma-27b-it",
    "12b": "google/translategemma-12b-it",
}

# vLLM version pinned for reproducibility on unattended paid-GPU runs.
# NEEDS-VERIFICATION: confirm this version (a) is current/available and
# (b) actually supports TranslateGemma's architecture before the first real
# `run_batch` invocation — bump deliberately, never silently, and record the
# new pin + why in this file's history.
VLLM_VERSION = "0.11.0"
CUDA_BASE_IMAGE = "nvidia/cuda:12.4.1-devel-ubuntu22.04"

GPU_KIND = "H100"
MAX_MODEL_LEN = 4096
DEFAULT_MAX_NEW_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.1
GPU_MEMORY_UTILIZATION = 0.95

# Bounds vLLM's activation-peak + CUDA-graph reservation, which is what
# actually starved the KV cache on the 27B: measured 51.23 GiB of weights
# on an 80GB H100 left "Available KV cache memory: -0.62 GiB" at util=0.90
# with vLLM's default max_num_seqs (256). 32 concurrent sequences is far
# more than the bakeoff needs and leaves comfortable KV headroom; raise it
# deliberately for the C3 throughput grid, where concurrency is the variable
# under test and the cost of a failed launch is understood.
MAX_NUM_SEQS = 32

# Idle-container timeout for cost control. A 27B BF16 model load from the
# volume is itself a multi-minute operation, so this is deliberately not a
# 10-second hair-trigger (that would just convert idle-GPU cost into
# repeated cold-start cost); it is still short relative to a full workday.
SCALEDOWN_WINDOW_SECONDS = 180
STARTUP_TIMEOUT_SECONDS = 900
TRANSLATE_TIMEOUT_SECONDS = 3600

# H100 list price, $/GPU-hour. NEEDS-VERIFICATION: confirm current Modal
# list price at modal.com/pricing before trusting any $ estimate this
# script prints — this is a rough placeholder, not a billed number.
H100_LIST_PRICE_PER_HOUR_USD = 3.95
H100_LIST_PRICE_PER_SEC_USD = H100_LIST_PRICE_PER_HOUR_USD / 3600.0

# Hard caps so a malformed caller can't accidentally submit an unbounded
# batch to a paid GPU in one call. run_batch (below) chunks under this.
MAX_ITEMS_PER_CALL = 512
MAX_ARABIC_CHARS_PER_ITEM = 20_000
PROGRESS_EVERY_N_ITEMS = 25

DEFAULT_TEMPLATE = (
    "Translate the following Classical Arabic text into fluent, faithful "
    "English. Preserve names, numbers, dates, and quotations exactly. "
    "Output only the English translation, nothing else.\n\n"
    "Arabic:\n{arabic}\n\nEnglish:"
)

# --------------------------------------------------------------------------
# Modal app / image / volume / secret plumbing
# --------------------------------------------------------------------------

app = modal.App(APP_NAME)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
hf_secret = modal.Secret.from_name(HF_SECRET_NAME)

download_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface_hub[hf_transfer]==0.26.2",
).env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})

serve_image = (
    modal.Image.from_registry(CUDA_BASE_IMAGE, add_python="3.11")
    .pip_install(
        # vllm pins its own (newer) huggingface_hub — do not double-pin it here,
        # that made pip's resolution impossible. hf_transfer rides along unpinned.
        f"vllm=={VLLM_VERSION}",
        # ROOT CAUSE of the "rope_scaling should have a 'rope_type' key" crash
        # (4 failed smoke attempts, 2026-08-13): vllm 0.11.0 declares only
        # `transformers>=4.55.2` with NO upper bound, so pip installed
        # transformers 5.x, which renamed the rope config `rope_scaling` ->
        # `rope_parameters`. vllm's patch_rope_scaling() then sees a rope dict
        # without a 'rope_type' key and raises. Patching the model's
        # config.json does NOT help -- the mismatch is in how transformers
        # parses it, not in the file. Pin below the rename.
        "transformers<5",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_LOGGING_LEVEL": "INFO"})
)


# --------------------------------------------------------------------------
# Manifest helpers (shared by download + serve; run inside container fns)
# --------------------------------------------------------------------------

def _read_manifest() -> dict:
    p = Path(MANIFEST_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_manifest(manifest: dict) -> None:
    Path(MANIFEST_PATH).write_text(json.dumps(manifest, indent=2, sort_keys=True))


def _local_dir_for(model_key: str) -> str:
    return f"{WEIGHTS_MOUNT}/{model_key}"


# --------------------------------------------------------------------------
# Download function (CPU only — no GPU spend)
# --------------------------------------------------------------------------

@app.function(
    image=download_image,
    volumes={WEIGHTS_MOUNT: volume},
    secrets=[hf_secret],
    timeout=6 * 3600,
)
def download_weights(model_key: str = "27b", force: bool = False, revision: str | None = None) -> dict:
    """Snapshot a TranslateGemma repo into the shared volume.

    Idempotent: if the manifest already records this model_key (and the
    local dir looks populated) and force=False, this is a no-op that just
    returns the existing manifest entry. Revision-pinned: resolves the repo
    HEAD commit SHA once (unless an explicit `revision` is passed) and
    records exactly that SHA, so re-downloads and re-serves are
    reproducible even if the upstream repo changes later.
    """
    if model_key not in MODEL_REPOS:
        raise ValueError(f"unknown model_key {model_key!r}; choices: {sorted(MODEL_REPOS)}")

    from huggingface_hub import HfApi, snapshot_download

    repo_id = MODEL_REPOS[model_key]
    local_dir = _local_dir_for(model_key)
    manifest = _read_manifest()

    existing = manifest.get(model_key)
    already_present = existing is not None and Path(local_dir, "config.json").exists()
    if already_present and not force:
        print(f"[download_weights] {model_key} already present at {local_dir} "
              f"(revision {existing.get('revision')}); skipping (force=False).")
        return existing

    api = HfApi()
    pinned_revision = revision or api.model_info(repo_id).sha
    print(f"[download_weights] snapshotting {repo_id} @ {pinned_revision} -> {local_dir}")

    snapshot_download(
        repo_id=repo_id,
        revision=pinned_revision,
        local_dir=local_dir,
        max_workers=8,
    )

    entry = {
        "model_key": model_key,
        "repo_id": repo_id,
        "revision": pinned_revision,
        "local_dir": local_dir,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest[model_key] = entry
    _write_manifest(manifest)
    volume.commit()
    print(f"[download_weights] done: {entry}")
    return entry


# --------------------------------------------------------------------------
# Cheap CPU healthcheck — no GPU spend
# --------------------------------------------------------------------------

@app.function(image=download_image, volumes={WEIGHTS_MOUNT: volume}, timeout=60)
def check_weights_present(model_key: str = "27b") -> dict:
    volume.reload()
    manifest = _read_manifest()
    entry = manifest.get(model_key)
    present = entry is not None and Path(_local_dir_for(model_key), "config.json").exists()
    return {"model_key": model_key, "present": present, "manifest_entry": entry}


# --------------------------------------------------------------------------
# GPU-serving class: one model per container, vLLM native batching
# --------------------------------------------------------------------------

@app.cls(
    image=serve_image,
    gpu=GPU_KIND,
    volumes={WEIGHTS_MOUNT: volume},
    secrets=[hf_secret],
    min_containers=0,
    scaledown_window=SCALEDOWN_WINDOW_SECONDS,
    timeout=TRANSLATE_TIMEOUT_SECONDS,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
)
class TranslateGemmaServer:
    model_key: str = modal.parameter(default="27b")

    @modal.enter()
    def load(self) -> None:
        from vllm import LLM

        # NOTE (corrected 2026-08-14): an earlier version of this comment
        # claimed the "rope_scaling should have a 'rope_type' key" crash was
        # fixed by patching config.json on the weights volume. **That is
        # wrong and was never true.** Verified by pulling both configs off
        # the volume before the 12B run: `text_config.rope_scaling` is null
        # in BOTH 27b and 12b, unpatched and structurally identical, and
        # both serve fine. The fix that actually works is the
        # `transformers<5` pin in the image (see the image definition
        # above for the root cause). Patching config.json does NOT help --
        # three attempts proved that, because the mismatch is in how
        # transformers parses the field, not in the file. Do not re-patch
        # weights on the strength of this comment's earlier claim.
        volume.reload()
        manifest = _read_manifest()
        entry = manifest.get(self.model_key)
        if entry is None:
            raise RuntimeError(
                f"no weights_manifest.json entry for model_key={self.model_key!r}; "
                "run download_weights first."
            )
        local_dir = entry["local_dir"]
        if not Path(local_dir, "config.json").exists():
            raise RuntimeError(f"manifest says {local_dir} has weights but config.json is missing")

        self._manifest_entry = entry
        print(f"[TranslateGemmaServer] loading {entry['repo_id']} @ {entry['revision']} "
              f"from {local_dir} (vllm={VLLM_VERSION}, dtype=bfloat16, "
              f"max_model_len={MAX_MODEL_LEN})")
        t0 = time.monotonic()
        self.llm = LLM(
            model=local_dir,
            dtype="bfloat16",
            max_model_len=MAX_MODEL_LEN,
            gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
            max_num_seqs=MAX_NUM_SEQS,
            trust_remote_code=True,
        )
        self._tokenizer = self.llm.get_tokenizer()
        print(f"[TranslateGemmaServer] engine ready in {time.monotonic() - t0:.1f}s")

    @modal.method()
    def translate_batch(
        self,
        items: list[dict],
        template: str = DEFAULT_TEMPLATE,
        temperature: float = DEFAULT_TEMPERATURE,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        top_p: float = 1.0,
    ) -> dict:
        """Translate a batch of {id, arabic} items in one vLLM engine call.

        Returns {"results": [...], "metadata": {...}}. Every result has
        {id, english, output_tokens, latency_s} on success, or
        {id, english: None, error: str} on a per-item failure — one bad
        item never raises out of this function and sinks the whole batch.
        """
        from vllm import SamplingParams

        wall_t0 = time.monotonic()

        if not isinstance(items, list) or len(items) == 0:
            return {
                "results": [],
                "metadata": self._metadata(batch_size=0, num_ok=0, num_skipped=0,
                                            wall_time_s=0.0, sampling={}),
            }
        if len(items) > MAX_ITEMS_PER_CALL:
            raise ValueError(
                f"batch of {len(items)} exceeds MAX_ITEMS_PER_CALL={MAX_ITEMS_PER_CALL}; "
                "chunk on the caller side (see run_batch)."
            )

        reserved_for_output = max_new_tokens
        prompt_budget = MAX_MODEL_LEN - reserved_for_output

        prompts: list[str] = []
        prompt_ids: list[object] = []
        skipped: list[dict] = []

        for i, item in enumerate(items):
            if i % PROGRESS_EVERY_N_ITEMS == 0:
                print(f"[translate_batch] validating {i}/{len(items)}")
            try:
                item_id = item["id"]
                arabic = item["arabic"]
                if not isinstance(arabic, str) or not arabic.strip():
                    raise ValueError("empty or non-string 'arabic' field")
                if len(arabic) > MAX_ARABIC_CHARS_PER_ITEM:
                    raise ValueError(
                        f"arabic field is {len(arabic)} chars, exceeds cap "
                        f"{MAX_ARABIC_CHARS_PER_ITEM}"
                    )
                prompt = template.format(arabic=arabic)
                n_tokens = len(self._tokenizer.encode(prompt))
                if n_tokens > prompt_budget:
                    raise ValueError(
                        f"prompt is {n_tokens} tokens, exceeds budget {prompt_budget} "
                        f"(max_model_len={MAX_MODEL_LEN} - max_new_tokens={max_new_tokens})"
                    )
                prompts.append(prompt)
                prompt_ids.append(item_id)
            except Exception as exc:  # noqa: BLE001 — deliberate: one bad item must not sink the batch
                skipped.append({
                    "id": item.get("id") if isinstance(item, dict) else None,
                    "english": None,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        results: list[dict] = list(skipped)

        if prompts:
            sampling = SamplingParams(
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_new_tokens,
            )
            gen_t0 = time.monotonic()
            outputs = self.llm.generate(prompts, sampling, use_tqdm=True)
            gen_wall = time.monotonic() - gen_t0
            per_item_latency = gen_wall / len(prompts)  # even-split fallback; see below

            for i, (item_id, output) in enumerate(zip(prompt_ids, outputs)):
                if i % PROGRESS_EVERY_N_ITEMS == 0:
                    print(f"[translate_batch] collecting {i}/{len(outputs)}")
                try:
                    text = output.outputs[0].text.strip()
                    n_out_tokens = len(output.outputs[0].token_ids)
                    latency_s = per_item_latency
                    try:
                        # vLLM RequestOutput.metrics carries real per-request
                        # timing on versions that support it; fall back to the
                        # even-split estimate above if the field is absent or
                        # shaped differently across vllm versions.
                        m = output.metrics
                        if m is not None and m.finished_time and m.arrival_time:
                            latency_s = m.finished_time - m.arrival_time
                    except Exception:  # noqa: BLE001, S110 — metrics API varies by vllm version; even-split fallback above already set
                        pass
                    results.append({
                        "id": item_id,
                        "english": text,
                        "output_tokens": n_out_tokens,
                        "latency_s": round(latency_s, 4),
                    })
                except Exception as exc:  # noqa: BLE001 — same guard, post-processing side
                    results.append({
                        "id": item_id,
                        "english": None,
                        "error": f"postprocess {type(exc).__name__}: {exc}",
                    })

        wall_time_s = time.monotonic() - wall_t0
        metadata = self._metadata(
            batch_size=len(items),
            num_ok=sum(1 for r in results if r.get("english") is not None),
            num_skipped=len(items) - sum(1 for r in results if r.get("english") is not None),
            wall_time_s=round(wall_time_s, 4),
            sampling={"temperature": temperature, "top_p": top_p, "max_new_tokens": max_new_tokens},
        )
        return {"results": results, "metadata": metadata}

    def _metadata(self, *, batch_size: int, num_ok: int, num_skipped: int,
                   wall_time_s: float, sampling: dict) -> dict:
        entry = getattr(self, "_manifest_entry", {})
        return {
            "app": APP_NAME,
            "model_key": self.model_key,
            "repo_id": entry.get("repo_id"),
            "revision": entry.get("revision"),
            "engine": "vllm",
            "vllm_version": VLLM_VERSION,
            "dtype": "bfloat16",
            "max_model_len": MAX_MODEL_LEN,
            "gpu": GPU_KIND,
            "batch_size": batch_size,
            "num_ok": num_ok,
            "num_skipped": num_skipped,
            "wall_time_s": wall_time_s,
            "sampling": sampling,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# --------------------------------------------------------------------------
# Local entrypoints
# --------------------------------------------------------------------------

# Two centuries-old public-domain classical Arabic lines, hardcoded only for
# an end-to-end serving smoke test. Not sourced from ATHAR/LK-Hadith/
# hadith-json (see repo HARD RULES on rights hygiene) — these are a
# well-known Qur'anic opening phrase and a well-known pre-modern proverb,
# both long public domain, used purely to prove the pipeline runs.
_SMOKE_ITEMS = [
    {"id": "smoke-1", "arabic": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"},
    {"id": "smoke-2", "arabic": "الْعِلْمُ فِي الصِّغَرِ كَالنَّقْشِ فِي الْحَجَرِ"},
]


@app.local_entrypoint()
def smoke(model_key: str = "27b") -> None:
    """CPU healthcheck, then a real 2-line GPU translate call. Spins paid
    GPU time (see README.md) unless weights are missing, in which case it
    stops before touching the GPU."""
    print(f"[smoke] checking weights for model_key={model_key!r} ...")
    status = check_weights_present.remote(model_key)
    if not status["present"]:
        print(f"[smoke] ABORT: weights not present for {model_key!r}. "
              f"Run: modal run throughput/serve_translategemma.py::download_weights "
              f"--model-key {model_key}")
        return
    print(f"[smoke] weights present: {status['manifest_entry']}")

    server = TranslateGemmaServer(model_key=model_key)
    print(f"[smoke] translating {len(_SMOKE_ITEMS)} hardcoded public-domain lines ...")
    t0 = time.monotonic()
    out = server.translate_batch.remote(_SMOKE_ITEMS, DEFAULT_TEMPLATE)
    wall_s = time.monotonic() - t0

    for r in out["results"]:
        print(f"  id={r['id']!r} -> {r.get('english')!r} "
              f"(tokens={r.get('output_tokens')}, latency_s={r.get('latency_s')}, "
              f"error={r.get('error')})")
    print(f"[smoke] metadata: {json.dumps(out['metadata'], indent=2)}")

    est_cost = wall_s * H100_LIST_PRICE_PER_SEC_USD
    print(f"[smoke] rough client-side wall time: {wall_s:.1f}s "
          f"(includes any cold start) -> est. ${est_cost:.4f} at "
          f"${H100_LIST_PRICE_PER_HOUR_USD}/H100-hr [NEEDS-VERIFICATION price]. "
          "This is NOT a saturated-throughput measurement — see C3 for that.")


@app.local_entrypoint()
def run_batch(
    input: str,
    output: str,
    model_key: str = "27b",
    chunk_size: int = 128,
    temperature: float = DEFAULT_TEMPERATURE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> None:
    """Translate a jsonl file of {id, arabic} items, chunked to respect
    MAX_ITEMS_PER_CALL, writing results incrementally so a mid-run failure
    doesn't lose completed chunks. Input/output should live under
    /Volumes/Nodes/versed-translator/{benchmark-data,runs}/... — never
    inside this repo (see README.md)."""
    in_path = Path(input)
    out_path = Path(output)
    if not in_path.exists():
        raise FileNotFoundError(in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    items = []
    with in_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    print(f"[run_batch] loaded {len(items)} items from {in_path}")

    if chunk_size > MAX_ITEMS_PER_CALL:
        chunk_size = MAX_ITEMS_PER_CALL
        print(f"[run_batch] chunk_size capped to MAX_ITEMS_PER_CALL={MAX_ITEMS_PER_CALL}")

    server = TranslateGemmaServer(model_key=model_key)
    run_started = datetime.now(timezone.utc).isoformat()
    total_wall_s = 0.0
    n_ok = 0
    n_err = 0

    with out_path.open("w") as out_f:
        for start in range(0, len(items), chunk_size):
            chunk = items[start:start + chunk_size]
            print(f"[run_batch] chunk {start}-{start + len(chunk)} of {len(items)} ...")
            t0 = time.monotonic()
            out = server.translate_batch.remote(chunk, DEFAULT_TEMPLATE, temperature, max_new_tokens)
            chunk_wall_s = time.monotonic() - t0
            total_wall_s += chunk_wall_s
            for r in out["results"]:
                out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
                if r.get("english") is not None:
                    n_ok += 1
                else:
                    n_err += 1
            out_f.flush()
            print(f"[run_batch] chunk done in {chunk_wall_s:.1f}s "
                  f"(metadata: {out['metadata']})")

        out_f.write(json.dumps({
            "_run_summary": {
                "input": str(in_path),
                "output": str(out_path),
                "model_key": model_key,
                "started_at": run_started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "n_items": len(items),
                "n_ok": n_ok,
                "n_err": n_err,
                "total_wall_s": round(total_wall_s, 2),
                "est_cost_usd": round(total_wall_s * H100_LIST_PRICE_PER_SEC_USD, 4),
                "price_constant_needs_verification": H100_LIST_PRICE_PER_HOUR_USD,
            }
        }, ensure_ascii=False) + "\n")

    print(f"[run_batch] wrote {len(items)} results ({n_ok} ok, {n_err} error) to {out_path}")
    print(f"[run_batch] total GPU wall time (client-observed): {total_wall_s:.1f}s "
          f"-> est. ${total_wall_s * H100_LIST_PRICE_PER_SEC_USD:.4f} "
          f"[NEEDS-VERIFICATION price constant]")
