"""Hayy / Ockley: numbered English sections as coarse locks, then sentence DP.

Ockley's 120 printed sections are the hard anchors. Interior alignment is
variable-span monotonic DP. Embeddings are not in v0 — length is a prior,
names/numbers snap. The reader buffer (±1–2 sentences) is tolerance, not
the objective; we still store the finest span the DP justified.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from versed_translator.align.dp import Link, align
from versed_translator.align.sentences import split_paragraphs_arabic, split_paragraphs_english
from versed_translator.benchmark.sources import monotone_length, ockley_hayy
from versed_translator.benchmark.sources import openiti_markdown
from versed_translator.paths import DATA_DIR

WORK_ID = ockley_hayy.WORK_ID
DEFAULT_ARABIC = DATA_DIR / "openiti" / "0581IbnTufayl.HayyIbnYaqzan.txt"
DEFAULT_ENGLISH = DATA_DIR / "pd-english" / "ockley_hayy_pg16831.txt"
DEFAULT_OUT = DATA_DIR / "benchmark-alignment" / "hayy_ockley" / "sentence_spans.jsonl"


@dataclass(frozen=True)
class SectionAlignment:
    section_index: int
    printed_number: int
    arabic_paragraph_range: tuple[int, int]
    arabic_sentences: tuple[str, ...]
    english_sentences: tuple[str, ...]
    links: tuple[Link, ...]


def _arabic_paragraphs(path: Path) -> list[openiti_markdown.Paragraph]:
    text = openiti_markdown.read(path)
    section = next(
        section for section in text.sections if section.title == "حي بن يقظان"
    )
    return section.paragraphs


_YOKDHAN_STORY_EN = re.compile(
    r"Yokdh[aâà]n.{0,120}(?:Married|Princess|Sister|Ark|Child)"
    r"|(?:Married|Princess|Sister|Ark).{0,120}Yokdh[aâà]n",
    re.IGNORECASE | re.DOTALL,
)


def _first_where(items, predicate) -> int:
    for index, item in enumerate(items):
        if predicate(item):
            return index
    return 0


def align_book(
    arabic_path: Path,
    english_path: Path,
) -> list[SectionAlignment]:
    english = ockley_hayy.parse_english_sections(
        english_path.read_text(encoding="utf-8", errors="replace")
    )
    paragraphs = _arabic_paragraphs(arabic_path)
    # Ockley opens with a long natural-philosophy preface that is not the
    # Arabic birth narrative. Length-partitioning those together is how
    # we got 20 partials on Ibn Rushd; names are the coarse lock here.
    en_start = _first_where(
        english, lambda section: _YOKDHAN_STORY_EN.search(section.text)
    )
    ar_start = _first_where(
        paragraphs, lambda paragraph: "يقظان" in paragraph.text
    )
    ranges = monotone_length.partition(
        [section.word_count for section in english[en_start:]],
        [paragraph.word_count for paragraph in paragraphs[ar_start:]],
        min_fragments=1,
        max_fragments=8,
    )
    out: list[SectionAlignment] = []
    for offset, section in enumerate(english[:en_start]):
        en_sents = split_paragraphs_english([section.text])
        links = align([], [s.text for s in en_sents])
        out.append(
            SectionAlignment(
                section_index=offset,
                printed_number=section.printed_number,
                arabic_paragraph_range=(0, ar_start),
                arabic_sentences=(),
                english_sentences=tuple(s.text for s in en_sents),
                links=tuple(links),
            )
        )
    for index, section in enumerate(english[en_start:]):
        start, end = ranges[index]
        start += ar_start
        end += ar_start
        ar_sents = split_paragraphs_arabic(
            [paragraph.text for paragraph in paragraphs[start:end]]
        )
        en_sents = split_paragraphs_english([section.text])
        links = align([s.text for s in ar_sents], [s.text for s in en_sents])
        out.append(
            SectionAlignment(
                section_index=en_start + index,
                printed_number=section.printed_number,
                arabic_paragraph_range=(start, end),
                arabic_sentences=tuple(s.text for s in ar_sents),
                english_sentences=tuple(s.text for s in en_sents),
                links=tuple(links),
            )
        )
    return out


def summarise(sections: list[SectionAlignment]) -> dict[str, float | int]:
    links = [link for section in sections for link in section.links]
    skips = sum(1 for link in links if "skip" in link.flags)
    tight = sum(1 for link in links if link.uncertainty_radius == 0)
    return {
        "sections": len(sections),
        "links": len(links),
        "skip_links": skips,
        "radius_0": tight,
        "mean_confidence": (
            round(sum(link.confidence for link in links) / len(links), 3) if links else 0.0
        ),
        "arabic_sentences": sum(len(section.arabic_sentences) for section in sections),
        "english_sentences": sum(len(section.english_sentences) for section in sections),
    }


def write_jsonl(sections: list[SectionAlignment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for section in sections:
            handle.write(
                json.dumps(
                    {
                        "work_id": WORK_ID,
                        "section_index": section.section_index,
                        "printed_number": section.printed_number,
                        "arabic_paragraph_range": list(section.arabic_paragraph_range),
                        "arabic_sentences": list(section.arabic_sentences),
                        "english_sentences": list(section.english_sentences),
                        "links": [asdict(link) for link in section.links],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arabic", type=Path, default=DEFAULT_ARABIC)
    parser.add_argument("--english", type=Path, default=DEFAULT_ENGLISH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    sections = align_book(args.arabic, args.english)
    write_jsonl(sections, args.out)
    stats = summarise(sections)
    print(json.dumps({"out": str(args.out), **stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
