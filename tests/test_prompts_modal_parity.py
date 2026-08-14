"""Pin the Modal batch path's prompts to their registry entries.

The Modal serving path used to hardcode its own prompt instead of importing
the harness prompt registry (the Modal *image* genuinely cannot import this
package). That was a legitimate constraint, but it let the two drift
silently: both TranslateGemma legs recorded ``prompt_template_id: "v1"``
while actually sending a minimal instruction carrying none of the six
fidelity rules -- which made TranslateGemma-vs-Claude a prompt comparison as
much as a model comparison, without anyone noticing.

Two paths, two guarantees:

* ``run_batch`` still sends the hardcoded ``DEFAULT_TEMPLATE``. Pinned here
  to its registry entry ``modal_minimal_v1``, character for character.
* ``run_blocks`` (the D2e structured path) builds prompts through
  ``harness.modal_batch``, which returns the prompt and its label from one
  registry lookup. Pinned here by asserting the serving module contains no
  competing prompt literal and reaches the registry only through that module.

These read the Modal module's source rather than importing it, so they don't
depend on modal being importable in the test environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

from versed_translator.harness import modal_batch
from versed_translator.harness.prompts import (
    FIDELITY_RULES,
    MODAL_MINIMAL_V1_ID,
    MODAL_MINIMAL_V1_TEXT,
    TEMPLATES,
)

SERVE_PATH = (
    Path(__file__).resolve().parents[1] / "throughput" / "serve_translategemma.py"
)
SERVE_SRC = SERVE_PATH.read_text(encoding="utf-8")
SERVE_TREE = ast.parse(SERVE_SRC)


def _modal_assign(name: str):
    for node in ast.walk(SERVE_TREE):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node.value
    raise AssertionError(f"{name} not found in serve_translategemma.py")


def _modal_default_template() -> str:
    """Extract DEFAULT_TEMPLATE's literal value without importing modal."""
    return ast.literal_eval(_modal_assign("DEFAULT_TEMPLATE"))


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


# ---------------------------------------------------------------------------
# The structured path: the recorded label must be the label of what was sent.
# ---------------------------------------------------------------------------


def test_structured_path_gets_its_prompts_from_the_registry():
    """`run_blocks` must build prompts through harness.modal_batch, locally.

    If someone re-introduces a hardcoded structured prompt in the serving
    module, the label and the prompt get two sources of truth again -- which
    is exactly how the original mislabel happened.
    """
    assert "from versed_translator.harness import modal_batch" in SERVE_SRC
    assert "modal_batch.build_structured_chunks" in SERVE_SRC
    assert "modal_batch.build_fallback_chunks" in SERVE_SRC


def test_serving_module_defines_no_prompt_of_its_own_beyond_the_pinned_one():
    """Only DEFAULT_TEMPLATE may be a prompt literal in the serving module."""
    for node in ast.walk(SERVE_TREE):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        # A string that both instructs and interpolates Arabic is a prompt.
        if "{arabic}" in text and "Translate" in text:
            assert text == MODAL_MINIMAL_V1_TEXT, (
                "serve_translategemma.py defines a prompt other than the pinned "
                "DEFAULT_TEMPLATE; build it through harness.modal_batch instead"
            )
        assert "JSON array of objects" not in text, (
            "the structured system prompt is duplicated in the serving module"
        )


def test_recorded_label_matches_the_prompt_that_was_actually_sent():
    """The parity guarantee itself, exercised end to end on the builder.

    Both chunk builders return the prompt and the id together; a run summary
    records ``chunk.template_id``. So this asserts the pairing that makes that
    record honest: the structured label maps to the structured system prompt,
    and the fallback label maps to the pinned minimal text.
    """
    items = [{"id": "A#b0001", "arabic": "نص"}]

    structured = modal_batch.build_structured_chunks(items)[0]
    assert structured.template_id in TEMPLATES
    assert structured.system == TEMPLATES[structured.template_id].system

    fallback = modal_batch.build_fallback_chunks(items)[0]
    assert fallback.template_id == MODAL_MINIMAL_V1_ID
    assert fallback.user == MODAL_MINIMAL_V1_TEXT.format(arabic="نص")
    assert fallback.user == _modal_default_template().format(arabic="نص")


def test_structured_prompt_carries_the_fidelity_rules_the_minimal_one_lacks():
    """The measurable difference between the two labels, stated as a test."""
    structured = modal_batch.build_structured_chunks([{"id": "A#b0001", "arabic": "x"}])[0]
    for rule in FIDELITY_RULES:
        assert rule in structured.system
        assert rule not in _modal_default_template()
