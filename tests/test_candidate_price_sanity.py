"""Regression + aspirational guards for ghost-priced candidates.

Motivation: in the NVDA case (2026-05-21 analysis id=13), a stale pre-split
resistance level of $606 was paired with a real current price of ~$140.
`compute_candidates` happily emitted a take_profit candidate at $606 and the
sanitizer let it through because Check #5 only verifies direction polarity,
not magnitude. The LLM then anchored its action plan to $606.

This module pins down two pieces:

1. **Current behavior** — `distance_pct_from_current` is recorded faithfully
   even for ghost-priced facts. A test that passes today and that would
   regress if a future refactor stopped recording the distance.
2. **Desired hardening** — two `xfail(strict=True)` assertions describing how
   the gate *should* behave once someone adds a distance check. `strict=True`
   means: if the gap closes and these start passing, pytest reports XPASS as a
   failure, forcing whoever fixed the gap to remove the markers. That
   converts "silent fix" into "loud, auditable test flip" so the spec
   follow-up doesn't drift away unnoticed.

Threshold: handoff memo suggests `|distance_pct| > 50` as the gate. The exact
threshold belongs to the hardening PR, not to this test — the xfail tests
only assert "ghost gets filtered", not a specific threshold value.

See `project-next-session-handoff.md` (NVDA sanity test priority) and
`repo-nvda-presplit-ghost.md` (superseded hypothesis, but the underlying gap
is real).
"""
import pytest

from src.analysis.candidate_rules import compute_candidates
from src.analysis.facts import CandidateLevel, FactBundle, FactRecord
from src.analysis.sanitizer_v2 import sanitize_with_candidates


def _fact(id, value, type_="technical", label=""):
    return FactRecord(
        id=id, type=type_, label=label or id,
        value=value, display_value=str(value),
    )


def _candidate(
    id_, direction, price, strategies,
    tier="primary", distance=1.0,
    basis_fact_id="technical.resistance", basis_rule="resistance_touch",
):
    return CandidateLevel(
        id=id_, type="candidate", label=basis_rule, value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id=basis_fact_id, basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def _bundle(candidates, current_price=140.0):
    facts = [FactRecord(
        id="technical.current_price", type="technical", label="现价",
        value=current_price, display_value=f"${current_price:.2f}",
    )]
    return FactBundle(
        as_of="2026-05-24T00:00:00Z", market="us", stock_code="NVDA",
        facts=facts, candidates=candidates,
    )


# ---------------------------------------------------------------------------
# Current-behavior pins (pass today; regression guards if behavior changes)
# ---------------------------------------------------------------------------

def test_ghost_resistance_distance_is_recorded():
    """A ghost-priced resistance produces a candidate whose
    `distance_pct_from_current` reflects the magnitude. This is what a future
    distance gate would consume — if compute_candidates ever stops recording
    it, this test catches that regression."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.resistance", 606.0),  # NVDA pre-split ghost
    ]
    cands = compute_candidates(facts)
    rt = [c for c in cands if c.basis_rule == "resistance_touch"]
    assert len(rt) == 1
    # (606 - 140) / 140 * 100 ≈ 332.86
    assert 300 < rt[0].distance_pct_from_current < 400


def test_ghost_swing_low_distance_is_recorded_for_stop_loss_direction():
    """Mirror of the above for the stop_loss direction — a ghost swing_low
    near zero vs a real current price."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.swing_low_20d", 5.0),  # impossibly low
    ]
    cands = compute_candidates(facts)
    sl = [c for c in cands if c.basis_rule == "prev_swing_low"]
    assert len(sl) == 1
    # (5 - 140) / 140 * 100 ≈ -96.4
    assert sl[0].distance_pct_from_current < -90


# ---------------------------------------------------------------------------
# Aspirational hardening — xfail(strict=True). When the fix lands, remove
# the marker and the assertion stands on its own.
# ---------------------------------------------------------------------------

_GHOST_GATE_REASON = (
    "Ghost-price gate not yet implemented (NVDA pre-split bug surface). "
    "Spec follow-up: candidates whose |distance_pct_from_current| is "
    "implausibly large (handoff suggests >50%) should be tagged "
    "tier='filtered' so sanitizer Check #4 drops them. Once that gate "
    "lands in candidate_rules or facts_builder, this xfail flips to "
    "XPASS — strict=True will then fail the suite, forcing whoever shipped "
    "the gate to remove this marker and confirm the new behavior."
)

_SANITIZER_GATE_REASON = (
    "Sanitizer magnitude check (Check #10) not yet implemented. Even if a "
    "candidate slips through the upstream tier='filtered' assignment with "
    "the wrong magnitude, the sanitizer should refuse it at the bundle "
    "boundary. Same flip mechanics as the candidate-rules gate above."
)


@pytest.mark.xfail(strict=True, reason=_GHOST_GATE_REASON)
def test_ghost_resistance_should_be_marked_filtered():
    """Aspirational: a 4x-off resistance must not be `primary` tier."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.resistance", 606.0),
    ]
    cands = compute_candidates(facts)
    rt = [c for c in cands if c.basis_rule == "resistance_touch"]
    assert len(rt) == 1
    assert rt[0].tier == "filtered"


@pytest.mark.xfail(strict=True, reason=_GHOST_GATE_REASON)
def test_ghost_swing_low_should_be_marked_filtered():
    """Aspirational: a stop at 5% of current is a ghost; must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.swing_low_20d", 5.0),
    ]
    cands = compute_candidates(facts)
    sl = [c for c in cands if c.basis_rule == "prev_swing_low"]
    assert len(sl) == 1
    assert sl[0].tier == "filtered"


@pytest.mark.xfail(strict=True, reason=_SANITIZER_GATE_REASON)
def test_sanitizer_drops_item_pointing_at_ghost_candidate():
    """Aspirational: even if a primary-tier ghost survives candidate rules,
    the sanitizer must refuse the action plan item that points at it."""
    ghost = _candidate(
        "candidate.exit.ghost", "take_profit", 606.0,
        ["swing_trade"], tier="primary", distance=332.86,
    )
    bundle = _bundle([ghost], current_price=140.0)
    items = [{
        "candidate_id": "candidate.exit.ghost",
        "trigger_price": 606.0,
        "direction": "take_profit",
        "priority": 1,
        "evidence_refs": ["technical.resistance", "committee.pm_verdict"],
        "tier": "primary",
    }]
    out = sanitize_with_candidates(
        items, bundle, strategy="swing_trade", current_price=140.0,
    )
    assert out == []


# ---------------------------------------------------------------------------
# Negative case — make sure the aspirational gate doesn't over-fire on
# legitimate large moves (e.g. high-volatility names). When the real gate
# lands, this test ensures the threshold isn't accidentally too tight.
# ---------------------------------------------------------------------------

def test_legitimate_30pct_swing_target_is_primary_tier_today():
    """30% upside target on a high-volatility stock is realistic — must stay
    `primary`. This pins current behavior; whoever implements the gate must
    pick a threshold that does NOT trip on this case (handoff suggests 50%
    as the threshold; this test keeps that floor honest)."""
    facts = [
        _fact("technical.current_price", 100.0),
        _fact("technical.resistance", 130.0),  # +30%, realistic
    ]
    cands = compute_candidates(facts)
    rt = [c for c in cands if c.basis_rule == "resistance_touch"]
    assert len(rt) == 1
    assert rt[0].tier == "primary"
