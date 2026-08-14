"""Pin the Modal batch template to its registry entry.

The Modal serving path hardcodes its own prompt instead of importing the
harness prompt registry (it runs inside a Modal image where this package
isn't installed). That is a legitimate constraint, but it let the two drift
silently: both TranslateGemma legs recorded ``prompt_template_id: "v1"``
while actually sending a minimal instruction carrying none of the six
fidelity rules -- which made TranslateGemma-vs-Claude a prompt comparison as
much as a model comparison, without anyone noticing.

These tests make that drift impossible to repeat. They read the Modal
module's literal rather than importing it, so they don't depend on modal
being importable in the test environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

from versed_translator.harness.prompts import (
    FIDELITY_RULES,
    MODAL_MINIMAL_V1_TEXT,
    TEMPLATES,
)

SERVE_PATH = (
    Path(__file__).resolve().parents[1] / "throughput" / "serve_translategemma.py"
)


def _modal_default_template() -> str:
    """Extract DEFAULT_TEMPLATE's literal value without importing modal."""
    tree = ast.parse(SERVE_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "DEFAULT_TEMPLATE":
                return ast.literal_eval(node.value)
    raise AssertionError("DEFAULT_TEMPLATE not found in serve_translategemma.py")


def test_modal_template_matches_registry_entry():
    """The registry's record of what Modal sends must equal what Modal sends."""
    assert _modal_default_template() == MODAL_MINIMAL_V1_TEXT


def test_modal_template_carries_no_fidelity_rules():
    """Documents WHY the mislabel mattered, and fails if that changes.

    If the Modal template ever gains the fidelity rules, this test fails --
    which is the correct prompt to re-measure the bakeoff and update the
    experiments ledger, not to silently delete the assertion.
    """
    text = _modal_default_template()
    for rule in FIDELITY_RULES:
        assert rule not in text


def test_modal_template_is_not_v1():
    """The specific mislabel that confounded the bakeoff."""
    assert _modal_default_template() != TEMPLATES["v1"].system
