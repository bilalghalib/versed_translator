# Alignment bundle → listening-reader bridge

**Implementation date:** 2026-08-17  
**Artifact contract:** `versed.align.reader-timeline.v1`  
**Implementation:** `src/versed_translator/align/reader_bridge.py`

## Outcome

The missing ID bridge now exists as an offline, rights-neutral build step. It
composes a verified bilingual alignment bundle with an OpenITI portable audio
edition and produces deterministic reader events:

```text
audio chunk + milliseconds
  → OpenITI ledger word IDs
  → Arabic alignment sentence IDs
  → sentence/paragraph/structural links
  → English display payload + mode
```

It does **not** publish a book, mutate `edition.sqlite3`, write Supabase, or
decide public/private rights. A private owner can run the same bridge against a
book they control.

## Command

```bash
uv run versed-align bridge-reader \
  --bundle book.alignment.zip \
  --ledger /path/to/book/edition.sqlite3 \
  --out book.reader-timeline.json
```

The bundle is fully verified before any member is parsed. The SQLite ledger is
opened read-only. Output is atomic and refuses overwrite unless `--force` is
explicitly supplied.

## Inputs and source-of-truth boundaries

| Input | Owns |
| --- | --- |
| Alignment bundle | structural, paragraph, and sentence correspondence |
| `edition.sqlite3.words` | stable OpenITI block/word identity |
| `audio_chunks` + `audio_word_timings` | Fish chunk-relative playback time |
| Reader bridge | composition and conservative display mode only |
| Publishing application | ownership, visibility, redistribution, and release policy |

The bridge intentionally does not duplicate the existing Versed
ledger-to-canonical identity mapper. A later app adapter composes the portable
timeline's ledger IDs with that mapper's canonical `blocks` / `span_words`
UUIDs.

## Sentence-to-ledger recovery

The aligner and edition ledger are derived from the same OpenITI source but use
different objects: the aligner retains logical paragraphs and derived
sentences, while the audio edition retains physical blocks and word IDs.

The bridge therefore:

1. normalizes Unicode, Arabic diacritics, tatweel, punctuation, and common
   alif/ya variants;
2. expands ledger words into one ordered token stream;
3. finds each Arabic alignment paragraph monotonically in that stream;
4. finds each derived Arabic sentence inside its already-matched paragraph;
5. retains the exact ledger word IDs covered by that sentence;
6. joins those IDs to Fish timings and emits one event per intersected chunk.

It does not fuzzy-match repeated phrases or jump backward. Unmapped paragraphs
and sentences are reported by stable ID rather than guessed.

Punctuation-only alignment artifacts such as `"."`, `"!"`, `"؟"`, or the
OpenITI `"|"` marker are reported separately as nonlexical; they do not count
against lexical sentence coverage and cannot generate a listening event.

## Structural clamp: what is actually asserted

The invariant is set membership in the explicit structural link:

```text
rendered Arabic structures ⊆ link.arabic_structure_ids
rendered English structures ⊆ link.english_structure_ids
```

Literal numeric prefix equality is **not** the invariant. A generic explicit
map may validly pair `ar:u0001` with `en:u0009`. The bridge accepts that pair
and rejects a render of `en:u0010`.

The same `assert_event_structural_clamp()` function runs while the timeline is
built and is exported for the app adapter to call again immediately before
rendering. `wrong_section` in a pilot is therefore a P0: either a structural
pair is wrong or a consumer bypassed the assertion.

## Three display modes

The provisional policy separates alignment uncertainty from subtitle length:

| Mode | Reader behavior | Provisional selection |
| --- | --- | --- |
| 1 — sentence highlight | Highlight linked English sentence(s) | radius 0–1, widened target ≤3 sentences, no low-signal/review/note flags |
| 2 — paragraph follow | Scroll matching paragraph into view; no sentence highlight | coarse container, low signal, radius/length over budget |
| 3 — section anchor | Show the paired section without local tracking | unanchored/review-required, excluded note, or no renderable English target |

Mode 2 removes a precision claim; it does **not** make a wrong paragraph
correct. Mode 3 is the structural safety floor.

The stored numeric value is emitted as `score_confidence`, explicitly marked
`uncalibrated_score_not_probability`. The provisional rule still consumes the
old radius bucket because the pilot has not yet fitted a better selector. That
is a temporary policy input, not an accuracy claim.

## Footnote guards

There are two distinct populations and two distinct guards:

1. Correctly detected English notes have `exclude_from_alignment`; they never
   enter DP. Mode-2 paragraph payloads carry paragraph flags and
   `exclude_from_alignment`, so the renderer can skip them while walking the
   paragraph sequence.
2. Missed notes are unflagged ordinary DP input. The bridge cannot identify
   them by checking a nonexistent flag; low-signal/coarse evidence demotes the
   link to mode 2. Pilot judgments must reveal the remaining misses.

Nothing is silently deleted. Flagged note text remains in the bundle for audit
and later tap-for-gloss behavior.

## Coverage metrics

The timeline reports both measures requested for launch decisions:

- `mode_1_link_coverage`: fraction of timed sentence links assigned mode 1;
- `mode_1_audio_time_coverage`: fraction of all complete Arabic audio
  milliseconds occupied by mode-1 event intervals.

It also reports link counts and mapped audio milliseconds for every mode. The
time metric uses the union of intervals per chunk, so overlapping spans are not
double-counted. Long paragraphs can therefore dominate listening-time coverage
without pretending to be many links.

Coverage is still not accuracy. Accuracy remains whatever the verified bundle
manifest declares, normally `unscored` until independent gold exists.

## Verification results

### Unit and contract tests

```text
tests/test_reader_bridge.py: 8 passed
reader bridge + bundle regression slice: 18 passed
targeted Ruff: passed
full repository suite: 528 passed, 24 skipped
```

The tests cover:

- audio milliseconds → Arabic ID → English ID composition;
- mode-1 link and audio-time coverage;
- explicit structural pairs with different unit numbers;
- cross-section render rejection;
- mode-2 low-signal demotion;
- mode-3 unanchored/review demotion;
- invalid timing beyond chunk duration;
- deterministic atomic output and overwrite refusal.

### Real Hamadhani corpus check

The reviewed Hamadhani bundle was bridged against a freshly prepared,
throwaway Versed OpenITI edition produced by the real edition parser:

| Measure | Result |
| --- | ---: |
| Alignment bundle | `hamadhani-prendergast-reviewed-v4.zip` |
| Bundle ID | `d4cab29b9c3bdae61d91c436cc78be1abbc062e866db0a4e603ef085e5eaec70` |
| Ledger Arabic words | 25,115 |
| Alignment Arabic sentences | 971 |
| Lexical Arabic sentences | 948 |
| Lexical sentences mapped to ledger words | **948 / 948 (100%)** |
| Unmapped Arabic paragraphs | **0** |
| Nonlexical punctuation/marker spans | 23, reported separately |

That temporary edition intentionally had no generated audio, so this check
proves text/ID recovery but does not invent listening-time coverage. Synthetic
fixtures exercise real `audio_chunks` / `audio_word_timings` rows and verify
the time calculations. A real Hamadhani audio edition will provide the honest
corpus-level time-weighted number.

## Pilot labels and launch gate

The end-to-end pilot comes after a real timed timeline can be rendered. Sample
40 listening events across modes, prose/verse, long/short spans, notes, and
operations. Record the visible mode and audio position, then label:

```text
sentence_ok | paragraph_only | section_only | wrong_section
```

Report outcomes by stratum. Compare mode-selection rules at matched precision,
not merely by how many links each rule calls mode 1; otherwise a permissive
rule can inflate its apparent coverage by making more false precision claims.

Choose the mode-1 eligibility and zero-cross-section launch thresholds before
looking at pilot results. Exact-span gold remains a separate, stricter ATHAR
dataset task on the same stable IDs.

## Remaining boundary

The bridge is landed; the frontend renderer is not. The next app-side change
should be a narrow adapter that:

1. composes ledger word/block IDs with the existing canonical Versed identity
   map;
2. calls `assert_event_structural_clamp()` (or an exact TypeScript port) before
   rendering;
3. renders modes 1–3 and skips excluded paragraphs in mode 2;
4. records pilot labels with visible mode and audio position.

That adapter should be built after the concurrent Hayy publication/identity
work settles, so it consumes the final canonical mapping contract instead of
editing the same live path in parallel.
