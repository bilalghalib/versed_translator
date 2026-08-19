"""Hierarchical Arabic-English alignment and portable bilingual bundles."""

from versed_translator.align.bundle import verify_bundle, write_bundle
from versed_translator.align.dp import Link, align, buffer_hit
from versed_translator.align.engine import align_documents
from versed_translator.align.models import AlignmentResult, Document
from versed_translator.align.reader_bridge import (
    assert_event_structural_clamp,
    build_reader_timeline,
    write_reader_timeline,
)
from versed_translator.align.sentences import split_arabic, split_english

__all__ = [
    "AlignmentResult",
    "Document",
    "Link",
    "align",
    "align_documents",
    "assert_event_structural_clamp",
    "buffer_hit",
    "build_reader_timeline",
    "split_arabic",
    "split_english",
    "verify_bundle",
    "write_bundle",
    "write_reader_timeline",
]
