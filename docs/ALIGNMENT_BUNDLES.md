# Bilingual alignment bundles

For the full algorithm, architecture critique, test evidence, and reproducible
three-section Hamadhani sample, see
[`ALIGNMENT_ALGORITHM_REVIEW.md`](ALIGNMENT_ALGORITHM_REVIEW.md).
For audio-time composition and the three-mode reader policy, see
[`READER_ALIGNMENT_BRIDGE.md`](READER_ALIGNMENT_BRIDGE.md).

`versed-align` builds a portable, checksummed zip without writing to a Versed
edition, Supabase, or a rights ledger. It stores three different relationships
instead of flattening them into one translation string:

1. bilateral structural units, such as maqama ↔ maqama;
2. Arabic paragraph span ↔ English paragraph span;
3. Arabic sentence span ↔ English sentence span.

The aligner is rights-neutral. A private owner can align a text they control;
the application that publishes or redistributes a bundle owns that policy.

## Build a listening-reader timeline

Once an OpenITI portable edition has Arabic audio timings, compose it with the
verified bundle without mutating either input:

```bash
uv run versed-align bridge-reader \
  --bundle book.alignment.zip \
  --ledger /path/to/book/edition.sqlite3 \
  --out book.reader-timeline.json
```

The output maps audio milliseconds through ledger word IDs and Arabic sentence
IDs to English sentence/paragraph payloads. It includes build-time structural
clamp assertions, provisional display modes, and both link-weighted and
audio-time-weighted mode coverage.

## Run the maqama profile

```bash
uv run versed-align build-maqama \
  --arabic ~/versed-translator-data/openiti/0398BadicZamanHamadhani.Maqamat.txt \
  --english ~/versed-translator-data/pd-english/prendergast_hamadhani_1915_djvu.txt \
  --embedding-model \
  --out ~/versed-translator-data/aligned/hamadhani-prendergast.zip

uv run versed-align verify \
  ~/versed-translator-data/aligned/hamadhani-prendergast.zip
```

The maqama profile is a structural shape, not a Hamadhani special case. It
requires both sides to expose the same count and requires at least 25% of the
heading pairs (minimum three) to confirm independently by transliteration or a
known translated epithet. Equal counts alone are rejected.

`--embedding-model` uses the local multilingual default
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Pass a model id
or local directory after the flag to override it. Omit the flag only for
diagnostic heuristic runs; those links are marked `heuristic_only`.

## Any other book

For an OpenITI source and a prepared plain-English translation, use the
book-agnostic entry point:

```bash
uv run versed-align build-text \
  --arabic openiti-book.txt \
  --english translation.txt \
  --embedding-model \
  --out book.alignment.zip
```

This retains the Arabic section hierarchy but does not invent a matching
English spine. It emits one low-confidence `whole_book_unanchored` structural
window marked `review_required`. If that window exceeds the DP cell boundary,
normalize the inputs and supply explicit structural anchors instead.

For maximum control, normalize both sides to `versed.align.document.v1` JSON
and optionally provide a JSONL structural map:

```bash
uv run versed-align build \
  --arabic-document arabic.document.json \
  --english-document english.document.json \
  --structural-map structures.jsonl \
  --embedding-model \
  --out book.alignment.zip
```

A minimal normalized document looks like:

```json
{
  "schema": "versed.align.document.v1",
  "work_id": "shared-work-id",
  "language": "ar",
  "source_name": "book.txt",
  "source_hash": "64-lowercase-hex-sha256-of-source",
  "structures": [{
    "id": "ar:u0000",
    "sequence": 0,
    "heading": "",
    "paragraphs": [{"id": "ar:u0000:p0000", "sequence": 0, "text": "..."}]
  }]
}
```

Each document contains ordered structural units, and each structural unit
contains ordered paragraphs. Paragraph ids must be unique and their source
hashes, when supplied, must match the normalized text. If there is no
structural map, the engine can run one explicitly low-confidence whole-book
window, subject to the DP cell limit. Large books should add anchors rather
than raise that limit casually.

## Bundle contents

```text
manifest.json
README.txt
documents/ar.structures.jsonl
documents/en.structures.jsonl
documents/ar.sentences.jsonl
documents/en.sentences.jsonl
alignments/structural.jsonl
alignments/paragraphs.jsonl
alignments/sentences.jsonl
reports/diagnostics.json
reports/accuracy.json
```

The zip is deterministic: fixed member names, fixed timestamps, sorted JSON,
SHA-256 for every payload, and atomic replacement. `verify` rejects duplicate,
undeclared, unsafe, size-mismatched, or checksum-mismatched members.

## Accuracy is separate from coverage

Without an independent gold JSONL, `reports/accuracy.json` says `unscored`.
Successful execution, 100% source coverage, or a clean zip is never reported as
sentence accuracy.

Gold rows use stable sentence ids:

```json
{"id":"g1","arabic_sentence_ids":["ar:u0001:p0002:s0000"],"english_sentence_ids":["en:u0001:p0003:s0000","en:u0001:p0003:s0001"]}
```

With gold, the scorecard reports exact span, ±1, ±2, correct paragraph,
catastrophic miss, and re-anchor distance. This is the accuracy contract for
comparing algorithms on the same book.

Per-link `confidence` is currently an internal ranking score mapped to 0–1,
not a calibrated probability. Only independent gold supports an accuracy
claim. The reader timeline therefore exposes it as `score_confidence`.

## Current limitation

OCR cleanup remains an adapter responsibility. The generic maqama adapter
removes repeated running heads and marks likely scholarly footnotes, but it
retains them in the document for audit. No generic regex can reliably separate
all nineteenth-century notes from translated prose. Semantic alignment helps;
independent gold is still required before claiming accuracy.
