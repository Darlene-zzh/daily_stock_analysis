# -*- coding: utf-8 -*-
"""Persona prompt-contract tests (Sprint 1A Task 1A-2).

Every master lens's ``system_prompt`` must satisfy the safety + schema
contract described in spec §7:

- Contains "**<Lens Name>**" — the bold lens label.
- Contains "analyst applying" framing.
- Refers to the canonical practitioner by full name once (so the lens has
  provenance).
- Forbids first-person impersonation explicitly.
- Contains the curated 5 tool names.
- Contains the persona's three tenets.
- Embeds the output JSON skeleton with the correct ``persona`` id.
- Token budget ≤ 2 000 tokens (approximate: <= 8 000 characters).
- Output voice is third-person analyst ("The position appears…").

PERSONA_DISPLAY mapping and DEFAULT_PERSONA_ORDER are also asserted as a
single source of truth.
"""
from __future__ import annotations

import json
import pytest

from src.agent.agents.master_personas import (
    DEFAULT_PERSONA_ORDER,
    PERSONA_DISPLAY,
    PERSONA_REGISTRY,
    CathieWoodLens,
    MichaelBurryLens,
    NassimTalebLens,
    WarrenBuffettLens,
    get_persona_class,
)
from src.agent.agents.master_personas.base_persona import TOOL_NAMES_SPRINT1
from src.agent.protocols import AgentContext


PERSONA_CLASSES = [
    WarrenBuffettLens,
    MichaelBurryLens,
    CathieWoodLens,
    NassimTalebLens,
]


# --------------------------------------------------------------------------- #
# Registry / display mapping
# --------------------------------------------------------------------------- #


def test_persona_registry_contains_all_four():
    expected = {"warren_buffett", "michael_burry", "cathie_wood", "nassim_taleb"}
    assert set(PERSONA_REGISTRY.keys()) == expected
    assert set(DEFAULT_PERSONA_ORDER) == expected
    # Order is deterministic and matches the spec's reading order.
    assert DEFAULT_PERSONA_ORDER == [
        "warren_buffett",
        "michael_burry",
        "cathie_wood",
        "nassim_taleb",
    ]


def test_persona_display_table_has_all_keys():
    required_keys = {"display_en", "display_zh", "avatar_initials", "avatar_color"}
    for persona_id, entry in PERSONA_DISPLAY.items():
        assert persona_id in PERSONA_REGISTRY
        assert set(entry.keys()) == required_keys
        # Display strings non-empty
        assert entry["display_en"].strip()
        assert entry["display_zh"].strip()
        assert entry["avatar_initials"].strip()
        # Avatar colour is a hex code
        assert entry["avatar_color"].startswith("#")


def test_display_strings_use_inspired_lens_framing():
    # Spec §7 — display layer must read as "inspired lens", not real-person
    # endorsement.
    for persona_id, entry in PERSONA_DISPLAY.items():
        assert "inspired" in entry["display_en"].lower() or "lens" in entry["display_en"].lower(), (
            f"{persona_id} display_en must use inspired-lens framing, got {entry['display_en']!r}"
        )


def test_get_persona_class_returns_correct_class():
    assert get_persona_class("warren_buffett") is WarrenBuffettLens
    assert get_persona_class("michael_burry") is MichaelBurryLens
    assert get_persona_class("cathie_wood") is CathieWoodLens
    assert get_persona_class("nassim_taleb") is NassimTalebLens
    with pytest.raises(KeyError):
        get_persona_class("unknown_persona_id")


# --------------------------------------------------------------------------- #
# system_prompt contract — applied to every persona
# --------------------------------------------------------------------------- #


def _make_ctx() -> AgentContext:
    return AgentContext(stock_code="600519", stock_name="贵州茅台", meta={"market": "A"})


@pytest.mark.parametrize("persona_cls", PERSONA_CLASSES, ids=lambda c: c.persona_id)
def test_persona_system_prompt_contract(persona_cls):
    ctx = _make_ctx()
    prompt = persona_cls.system_prompt(ctx)
    assert isinstance(prompt, str)
    # Spec §7 critical assertions

    # Inspired-lens framing — bold lens label present
    assert f"**{persona_cls.display_en}**" in prompt, (
        f"{persona_cls.persona_id} prompt missing bold lens label"
    )
    # Analyst framing
    assert "analyst" in prompt.lower()
    assert "applying" in prompt.lower()
    # Provenance (canonical practitioner) — must be in the prompt once
    assert persona_cls._associated_person() in prompt
    # First-person impersonation explicitly forbidden
    assert "never use first-person voice" in prompt
    # Third-person voice example
    assert "third-person" in prompt
    # Curated tool list present
    for tool in TOOL_NAMES_SPRINT1:
        assert tool in prompt, f"prompt missing tool {tool!r}"
    # Output JSON schema embedded with correct persona id
    assert f'"persona": "{persona_cls.persona_id}"' in prompt
    assert '"verdict"' in prompt
    assert '"score"' in prompt
    assert '"key_evidence"' in prompt
    # All three lens tenets present
    for tenet in persona_cls.tenets:
        # Use a short distinctive snippet from each tenet to be resilient to
        # whitespace differences.
        snippet = tenet.split(".")[0][:40].strip()
        assert snippet in prompt, f"persona {persona_cls.persona_id} missing tenet snippet {snippet!r}"
    # Out-of-scope guard present when defined
    if persona_cls.out_of_scope_guard:
        assert "scope" in prompt.lower()
    # Token budget — approximate via char-count, 1 token ≈ 4 chars worst case.
    # Cap at 8000 chars ≈ 2000 tokens (spec §6: "<= 2 000 tokens").
    assert len(prompt) <= 8000, (
        f"{persona_cls.persona_id} prompt {len(prompt)} chars (>~ 2k token budget)"
    )


@pytest.mark.parametrize("persona_cls", PERSONA_CLASSES, ids=lambda c: c.persona_id)
def test_persona_prompt_forbids_first_person_examples(persona_cls):
    """No first-person impersonation patterns in the example block."""
    prompt = persona_cls.system_prompt(_make_ctx())
    # These first-person patterns should NEVER appear in the prompt body —
    # they're explicitly listed as forbidden examples.
    # The prompt contains the literal forbidden EXAMPLE string
    # ("NOT \"I, Buffett, see…\"") so we check that 'I, ' followed by a name
    # appears at most as part of that pedagogical example.
    occurrences = prompt.count('"I, ')
    # Allowed exactly once (the example showing what NOT to do)
    assert occurrences <= 1, f"persona {persona_cls.persona_id} has too many 'I, NAME' patterns ({occurrences})"


# --------------------------------------------------------------------------- #
# build_user_message contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("persona_cls", PERSONA_CLASSES, ids=lambda c: c.persona_id)
def test_build_user_message_includes_report_and_stock(persona_cls):
    ctx = _make_ctx()
    report = {
        "summary": {"analysis_summary": "Strong franchise"},
        "details": {"fundamental_analysis": "ROE 25%"},
    }
    msg = persona_cls.build_user_message(ctx, report_json=report, tool_summary="ma, macd")
    assert "600519" in msg
    assert "贵州茅台" in msg
    assert "ma, macd" in msg
    # The actual report content should be embedded
    assert "Strong franchise" in msg


def test_build_user_message_truncates_huge_reports():
    """Spec note: weak models choke on enormous contexts."""
    ctx = _make_ctx()
    huge_report = {"summary": "x" * 50_000}
    msg = WarrenBuffettLens.build_user_message(ctx, report_json=huge_report)
    # Pre-analysis report JSON segment is hard-capped at 8000 chars
    assert "...(truncated)" in msg


def test_build_user_message_tolerates_non_serialisable_report():
    """Report blob with a non-JSON-serialisable object must not crash."""
    class NotJsonable:
        def __repr__(self) -> str:
            return "<NotJsonable>"

    ctx = _make_ctx()
    msg = WarrenBuffettLens.build_user_message(
        ctx, report_json={"bad": NotJsonable()}
    )
    # Either the default=str fallback serialised it, or the str() fallback fired.
    assert isinstance(msg, str)
    assert len(msg) > 0


# --------------------------------------------------------------------------- #
# Lens-specific tenet sanity (spec §7 mapping)
# --------------------------------------------------------------------------- #


def test_buffett_lens_emphasises_moat_and_intrinsic_value():
    prompt = WarrenBuffettLens.system_prompt(_make_ctx())
    lowered = prompt.lower()
    assert "moat" in lowered
    assert "intrinsic value" in lowered or "intrinsic-value" in lowered
    assert "circle of competence" in lowered


def test_burry_lens_emphasises_deep_value_and_catalysts():
    prompt = MichaelBurryLens.system_prompt(_make_ctx())
    lowered = prompt.lower()
    assert "deep value" in lowered or "deep-value" in lowered
    # Burry leans on hard cash-flow metrics + downside-first scepticism
    assert "free cash flow" in lowered or "fcf" in lowered
    assert "downside" in lowered


def test_cathie_wood_lens_emphasises_disruption_and_innovation():
    prompt = CathieWoodLens.system_prompt(_make_ctx())
    lowered = prompt.lower()
    assert "innovation" in lowered or "disruptive" in lowered
    assert "r&d" in lowered or "research" in lowered or "tam" in lowered


def test_taleb_lens_emphasises_tail_risk_and_convexity():
    prompt = NassimTalebLens.system_prompt(_make_ctx())
    lowered = prompt.lower()
    assert "tail" in lowered or "fat tail" in lowered or "blow-up" in lowered
    assert "convex" in lowered or "asymmetric" in lowered or "antifragile" in lowered


# --------------------------------------------------------------------------- #
# Determinism — system_prompt must be deterministic for a fixed ctx
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("persona_cls", PERSONA_CLASSES, ids=lambda c: c.persona_id)
def test_system_prompt_is_deterministic(persona_cls):
    ctx1 = _make_ctx()
    ctx2 = _make_ctx()
    assert persona_cls.system_prompt(ctx1) == persona_cls.system_prompt(ctx2)


# --------------------------------------------------------------------------- #
# JSON skeleton sanity — make sure the output example, when extracted, has
# valid JSON keys.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("persona_cls", PERSONA_CLASSES, ids=lambda c: c.persona_id)
def test_output_skeleton_has_all_required_keys(persona_cls):
    prompt = persona_cls.system_prompt(_make_ctx())
    # The skeleton lives between the first '{' after "no markdown" line and
    # the last '}'. We pull the skeleton substring and assert keys.
    needle = "no commentary outside JSON):\n{"
    start = prompt.find(needle)
    assert start != -1, "system_prompt schema skeleton marker missing"
    skeleton_block = prompt[start + len("no commentary outside JSON):\n") :]
    # Just check that required keys appear in the skeleton text — we can't
    # JSON-parse it directly because it's a documentation skeleton, not real
    # JSON.
    for key in ("persona", "verdict", "score", "headline", "rationale", "key_evidence", "tools_used"):
        assert f'"{key}"' in skeleton_block
    # Sanity that the JSON example's persona literal matches the class id
    assert f'"persona": "{persona_cls.persona_id}"' in skeleton_block
