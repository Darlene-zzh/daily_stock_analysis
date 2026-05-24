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


# ===========================================================================
# Group A — portfolio.avg_cost extreme values (cost-anchor ghosts)
# ===========================================================================
# `candidate_rules.py:205-234` gates only on `avg_cost > 0`. A broker CSV
# import bug that shifts the decimal point — a real failure mode for the
# Trading 212 importer landed in PR #10 — can produce:
#   * avg_cost = 99999 on a $140 stock → cost_plus_5/12/20% all way > current,
#     all 3 emit as `discipline_anchor` (line 221), anchoring the action plan
#     to $100k+ take_profit prices
#   * avg_cost = 0.01 on a $140 stock → cost_minus_10pct = $0.009 < current,
#     emits as `discipline_anchor` stop_loss (line 233) at sub-cent magnitude
#
# Aspirational gate: any cost-anchor whose |distance_pct_from_current| is
# implausibly large (handoff memo suggests >50% as the threshold) should be
# tagged `tier='filtered'` so the sanitizer drops it at the boundary.

_PORTFOLIO_GATE_REASON = (
    "Portfolio cost-anchor magnitude gate not yet implemented. "
    "candidate_rules.py:205-234 guards only `avg_cost > 0`; nothing bounds "
    "the resulting take_profit / stop_loss away from ghost magnitudes. "
    "Same xfail flip mechanics as the technical ghost-resistance test above."
)


def test_portfolio_avg_cost_inflated_take_profit_is_recorded_today():
    """A 700x-inflated avg_cost (decimal-shift broker bug) emits all three
    cost-anchor take_profit candidates at inflated prices today. Regression
    guard: if rule logic ever stops emitting these without an explicit gate,
    this test catches the silent change."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 99999.0, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    cost_anchors = [c for c in cands if c.basis_rule.startswith("cost_plus_")]
    assert len(cost_anchors) == 3  # +5%, +12%, +20%
    assert all(c.price > 100000 for c in cost_anchors)
    assert all(c.tier == "discipline_anchor" for c in cost_anchors)


def test_portfolio_avg_cost_tiny_value_stop_loss_is_recorded_today():
    """A 14000x-deflated avg_cost (reverse decimal-shift) emits a sub-cent
    cost_minus_10pct stop_loss today. The cost_plus_* candidates skip the
    `price > current` check and don't emit — only the stop path leaks."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 0.01, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    stop_anchors = [c for c in cands if c.basis_rule == "cost_minus_10pct"]
    assert len(stop_anchors) == 1
    assert stop_anchors[0].price < 0.05  # 0.01 * 0.9 = 0.009
    assert stop_anchors[0].tier == "discipline_anchor"


@pytest.mark.xfail(strict=True, reason=_PORTFOLIO_GATE_REASON)
def test_portfolio_avg_cost_inflated_should_be_filtered():
    """Aspirational: 700x-inflated cost anchors must be `filtered`, not
    `discipline_anchor`. Spec follow-up should add a magnitude gate either in
    candidate_rules (preferred — keeps sanitizer simple) or as a new
    sanitizer check parallel to Check #5."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 99999.0, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    cost_anchors = [c for c in cands if c.basis_rule.startswith("cost_plus_")]
    # Guard against vacuous-all XPASS: all([]) returns True, so if a future
    # refactor stops emitting these candidates, this test would XPASS for the
    # wrong reason and strict=True would break the suite. The paired pin test
    # above already verifies all 3 emit today.
    assert len(cost_anchors) == 3
    assert all(c.tier == "filtered" for c in cost_anchors)


@pytest.mark.xfail(strict=True, reason=_PORTFOLIO_GATE_REASON)
def test_portfolio_avg_cost_tiny_stop_loss_should_be_filtered():
    """Aspirational: a sub-cent stop_loss is a ghost; must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 0.01, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    stop_anchors = [c for c in cands if c.basis_rule == "cost_minus_10pct"]
    assert len(stop_anchors) == 1
    assert stop_anchors[0].tier == "filtered"


def test_portfolio_avg_cost_underwater_holder_stays_discipline_anchor():
    """An avg_cost of $120 on a stock at $100 (20% underwater holder) is a
    realistic position — cost_plus_* anchors above $100 must keep
    `discipline_anchor` tier. Pins the floor for the eventual gate: the
    magnitude threshold must NOT trip on plausible drawdowns or normal
    profit-taking anchors."""
    facts = [
        _fact("technical.current_price", 100.0),
        _fact("portfolio.avg_cost", 120.0, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    cost_anchors = [c for c in cands if c.basis_rule.startswith("cost_plus_")]
    # 120*1.05=126>100, 120*1.12=134.4>100, 120*1.20=144>100 → all three emit
    assert len(cost_anchors) == 3
    assert all(c.tier == "discipline_anchor" for c in cost_anchors)


# ===========================================================================
# Group B — quant.qlib_rank > 1.0 (corrupt percentile signal)
# ===========================================================================
# `candidate_rules.py:279-290` gates on `qlib_rank > 0.9` but has no upper
# bound. `quant.qlib_rank` is defined as a cross-sectional percentile in
# (0, 1] — any value > 1.0 is corrupt upstream data (qlib pipeline glitch,
# wrong scaling factor, etc.). The price itself isn't ghost (it's `current`),
# but the *signal source* is corrupt, and the action plan would still tell
# the user "Qlib 顶 10% 即时入场" off a broken metric.

_QLIB_GATE_REASON = (
    "qlib_rank upper-bound gate not yet implemented. quant.qlib_rank is a "
    "percentile in (0, 1] by spec — values > 1.0 indicate upstream data "
    "corruption and the candidate must be tier='filtered'. Fix can live in "
    "the extractor (reject the fact) or in candidate_rules (filter the "
    "candidate)."
)


def test_qlib_rank_above_one_emits_entry_candidate_today():
    """A corrupt qlib_rank=1.5 still emits a qlib_top_decile_buy entry today
    (passes the `> 0.9` guard, no upper bound). Regression guard: documents
    the current gap so a future fix is forced to flip the xfail below."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("quant.qlib_rank", 1.5, type_="quant", label="Qlib 截面分位"),
    ]
    cands = compute_candidates(facts)
    qlib_cands = [c for c in cands if c.basis_rule == "qlib_top_decile_buy"]
    assert len(qlib_cands) == 1
    assert qlib_cands[0].tier == "primary"


@pytest.mark.xfail(strict=True, reason=_QLIB_GATE_REASON)
def test_qlib_rank_above_one_should_be_filtered():
    """Aspirational: qlib_rank > 1.0 is corrupt; candidate must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("quant.qlib_rank", 1.5, type_="quant", label="Qlib 截面分位"),
    ]
    cands = compute_candidates(facts)
    qlib_cands = [c for c in cands if c.basis_rule == "qlib_top_decile_buy"]
    assert len(qlib_cands) == 1
    assert qlib_cands[0].tier == "filtered"


def test_qlib_rank_legit_top_decile_stays_primary():
    """A real qlib_rank=0.95 (legitimate top 5%) must keep `primary` tier.
    Pins floor for the gate: it must trigger on > 1.0 but NOT on valid
    percentiles inside (0.9, 1.0]."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("quant.qlib_rank", 0.95, type_="quant", label="Qlib 截面分位"),
    ]
    cands = compute_candidates(facts)
    qlib_cands = [c for c in cands if c.basis_rule == "qlib_top_decile_buy"]
    assert len(qlib_cands) == 1
    assert qlib_cands[0].tier == "primary"


# ===========================================================================
# Group C — chip.avg_cost zero / negative (sign-flip ghost)
# ===========================================================================
# `candidate_rules.py:292-302` gates on `chip_cost <= current` but never
# checks positivity. A zero or negative value — possible from broken Tushare
# response or sign flip in the chip extractor — passes the guard and emits
# an "entry" candidate at price 0 or negative. Anchoring buy orders to a
# zero price is exactly the failure mode this whole sanity layer exists to
# catch.

_CHIP_GATE_REASON = (
    "chip_avg_cost positivity gate not yet implemented. candidate_rules.py"
    ":292-302 only checks `chip_cost <= current`. Zero or negative values "
    "indicate upstream data corruption and must be tier='filtered'."
)


def test_chip_avg_cost_zero_emits_entry_at_zero_today():
    """chip.avg_cost = 0 passes the `<= current` guard and emits an entry
    candidate at price 0. Regression guard."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", 0.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].price == 0.0
    assert chip_cands[0].tier == "primary"


def test_chip_avg_cost_negative_emits_entry_at_negative_today():
    """chip.avg_cost = -5 passes (-5 <= 140) and emits a negative-priced
    entry candidate. Regression guard for the sign-flip case."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", -5.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].price == -5.0
    assert chip_cands[0].tier == "primary"


@pytest.mark.xfail(strict=True, reason=_CHIP_GATE_REASON)
def test_chip_avg_cost_zero_should_be_filtered():
    """Aspirational: chip.avg_cost == 0 is corrupt; candidate must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", 0.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].tier == "filtered"


@pytest.mark.xfail(strict=True, reason=_CHIP_GATE_REASON)
def test_chip_avg_cost_negative_should_be_filtered():
    """Aspirational: negative chip avg_cost is a sign-flip ghost; filter."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", -5.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].tier == "filtered"


def test_chip_avg_cost_legit_retest_stays_primary():
    """A real chip.avg_cost = $133 on a stock at $140 (legitimate -5% retest
    of market average cost) must stay `primary`. Pins floor: the gate must
    catch zero/negative but NOT normal retests within sensible ranges."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", 133.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].tier == "primary"


# ===========================================================================
# Group D — technical.support zero / negative (positivity ghost)
# ===========================================================================
# `candidate_rules.py:116-126` gates on `sup <= current` but never checks
# positivity. Mirror of the chip.avg_cost ghost in Group C: zero or negative
# support prices pass the guard and emit an entry candidate at $0 or negative.
# Same root failure mode (anchoring a buy order to a nonsense price), same
# aspirational fix (positivity check at the extractor or rules layer).

_SUPPORT_GATE_REASON = (
    "technical.support positivity gate not yet implemented. "
    "candidate_rules.py:116-126 guards only `sup <= current`. Zero or "
    "negative values indicate upstream data corruption and the candidate "
    "must be tier='filtered'."
)


def test_support_zero_emits_entry_at_zero_today():
    """technical.support = 0 passes the `<= current` guard and emits a
    support_test entry candidate at price 0. Regression guard."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", 0.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].price == 0.0
    assert sup_cands[0].tier == "primary"


def test_support_negative_emits_entry_at_negative_today():
    """technical.support = -10 passes (-10 <= 140) and emits a
    negative-priced entry. Sign-flip / corrupt-source regression guard."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", -10.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].price == -10.0
    assert sup_cands[0].tier == "primary"


@pytest.mark.xfail(strict=True, reason=_SUPPORT_GATE_REASON)
def test_support_zero_should_be_filtered():
    """Aspirational: technical.support == 0 is corrupt; must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", 0.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].tier == "filtered"


@pytest.mark.xfail(strict=True, reason=_SUPPORT_GATE_REASON)
def test_support_negative_should_be_filtered():
    """Aspirational: negative support is corrupt; must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", -10.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].tier == "filtered"


def test_support_legit_retest_stays_primary():
    """A real technical.support = $130 on a stock at $140 (legitimate -7%
    retest) must stay `primary`. Pins floor: the eventual positivity gate
    must NOT trip on normal pullback levels."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", 130.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].tier == "primary"


# ===========================================================================
# Group F — technical.atr_14 unguarded ghosts (zero / negative / inflated)
# ===========================================================================
# `candidate_rules.py:128-151` is the most permissive guard in the file:
# both `atr_2x_below_current` and `atr_3x_below_current` emit unconditionally
# when `atr is not None`. There is no positivity check, no upper bound, no
# polarity sanity. Three distinct ghost shapes:
#
#   * `atr = 0` → stop_loss collapses to `current` itself (zero protection
#     stop; would never trigger, but the action plan still anchors to it)
#   * `atr = -50` → stop_loss = current - 2*(-50) = current + 100, *above*
#     current — polarity reversed. Sanitizer Check #5 (direction polarity)
#     would refuse it, but rules layer still emits.
#   * `atr = 99999` → stop_loss at a hugely negative price, AND cascades into
#     the R-multiple targets via the `stop_ref = current - 2*atr` fallback
#     (line 168-169), producing absurd take_profit prices.
#
# Aspirational gate: ATR must be positive AND within a reasonable range of
# current price (e.g. `0 < atr < current` — a stock can't have ATR larger
# than its own price under any sane definition).

_ATR_GATE_REASON = (
    "technical.atr_14 sanity gate not yet implemented. candidate_rules.py"
    ":128-151 emits stop_loss candidates whenever `atr is not None` with no "
    "positivity, magnitude, or polarity check. Aspirational: atr must be "
    "positive and bounded (< current) or the resulting candidates must be "
    "tier='filtered'."
)


def test_atr_zero_emits_stop_loss_at_current_today():
    """atr_14 = 0 produces an atr_2x stop_loss at exactly `current` —
    a useless stop that never triggers, but still emitted today."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 0.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2x) == 1
    assert atr2x[0].price == 140.0
    assert atr2x[0].tier == "primary"


def test_atr_negative_emits_stop_loss_above_current_today():
    """atr_14 = -50 (sign-flip corruption) produces stop_loss = current -
    2*(-50) = 240, ABOVE current. Direction polarity is reversed at the
    rules layer; sanitizer Check #5 would refuse it downstream, but the
    rules-layer test pins that nothing stops the emission here today."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", -50.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2x) == 1
    assert atr2x[0].price == 240.0  # > current — polarity reversed
    assert atr2x[0].tier == "primary"


def test_atr_inflated_emits_negative_priced_stop_loss_today():
    """atr_14 = 99999 produces atr_2x stop_loss at current - 199998 =
    -199858 — a deeply negative price. Cascades into R-multiple targets
    via the stop_ref fallback (candidate_rules.py:168-169) producing absurd
    take_profit prices too."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 99999.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2x) == 1
    assert atr2x[0].price < -100000


@pytest.mark.xfail(strict=True, reason=_ATR_GATE_REASON)
def test_atr_zero_should_be_filtered():
    """Aspirational: ATR == 0 means no volatility signal; stop candidates
    derived from it are meaningless and must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 0.0),
    ]
    cands = compute_candidates(facts)
    atr_cands = [c for c in cands if c.basis_fact_id == "technical.atr_14"]
    assert len(atr_cands) >= 1
    assert all(c.tier == "filtered" for c in atr_cands)


@pytest.mark.xfail(strict=True, reason=_ATR_GATE_REASON)
def test_atr_negative_should_be_filtered():
    """Aspirational: negative ATR is data corruption; rules layer must not
    emit polarity-reversed candidates regardless of downstream sanitizer."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", -50.0),
    ]
    cands = compute_candidates(facts)
    atr_cands = [c for c in cands if c.basis_fact_id == "technical.atr_14"]
    assert len(atr_cands) >= 1
    assert all(c.tier == "filtered" for c in atr_cands)


@pytest.mark.xfail(strict=True, reason=_ATR_GATE_REASON)
def test_atr_inflated_should_be_filtered():
    """Aspirational: ATR larger than current price is implausible by any
    sane definition; must be filtered before cascading into R-multiple."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 99999.0),
    ]
    cands = compute_candidates(facts)
    atr_cands = [c for c in cands if c.basis_fact_id == "technical.atr_14"]
    assert len(atr_cands) >= 1
    assert all(c.tier == "filtered" for c in atr_cands)


def test_atr_legit_value_stays_primary():
    """A real ATR = $5 on a $140 stock (~3.5% daily range, realistic for
    a liquid large-cap) produces stop_loss at $130 / $125 — both `primary`
    tier. Pins floor: the gate must catch zero/negative/huge but NOT
    normal ATR values."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 5.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    atr3x = [c for c in cands if c.basis_rule == "atr_3x_below_current"]
    assert len(atr2x) == 1 and len(atr3x) == 1
    assert atr2x[0].price == 130.0  # 140 - 2*5
    assert atr3x[0].price == 125.0  # 140 - 3*5
    assert atr2x[0].tier == "primary"
    assert atr3x[0].tier == "primary"


# ===========================================================================
# Group G — technical.ma10 / ma20 positivity ghosts
# ===========================================================================
# `candidate_rules.py:92-114` has two rules: `ma20_breakdown` (stop_loss
# when ma20 < current) and `ma10_pullback` (entry when ma10 <= current).
# Neither checks positivity. Zero or negative moving averages — possible
# from broken data or a sign flip — pass through and produce candidates
# at nonsense prices. Same shape as Group C and Group D, applied to the
# moving-average surfaces.

_MA_GATE_REASON = (
    "technical.ma10/ma20 positivity gate not yet implemented. "
    "candidate_rules.py:92-114 only checks inequality vs current. Zero or "
    "negative moving averages indicate upstream corruption and the "
    "resulting candidates must be tier='filtered'."
)


def test_ma20_zero_emits_stop_loss_at_zero_today():
    """ma20 = 0 passes `0 < current` and emits ma20_breakdown stop_loss at
    $0. Pin against future silent removal."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma20", 0.0),
    ]
    cands = compute_candidates(facts)
    ma20_cands = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(ma20_cands) == 1
    assert ma20_cands[0].price == 0.0
    assert ma20_cands[0].tier == "primary"


def test_ma10_negative_emits_entry_at_negative_today():
    """ma10 = -5 passes -5 <= current and emits ma10_pullback entry at -$5.
    Sign-flip regression guard."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma10", -5.0),
    ]
    cands = compute_candidates(facts)
    ma10_cands = [c for c in cands if c.basis_rule == "ma10_pullback"]
    assert len(ma10_cands) == 1
    assert ma10_cands[0].price == -5.0
    assert ma10_cands[0].tier == "primary"


@pytest.mark.xfail(strict=True, reason=_MA_GATE_REASON)
def test_ma20_zero_should_be_filtered():
    """Aspirational: ma20 == 0 is corrupt; stop candidate must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma20", 0.0),
    ]
    cands = compute_candidates(facts)
    ma20_cands = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(ma20_cands) == 1
    assert ma20_cands[0].tier == "filtered"


@pytest.mark.xfail(strict=True, reason=_MA_GATE_REASON)
def test_ma10_negative_should_be_filtered():
    """Aspirational: negative ma10 is a sign-flip ghost; must be filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma10", -5.0),
    ]
    cands = compute_candidates(facts)
    ma10_cands = [c for c in cands if c.basis_rule == "ma10_pullback"]
    assert len(ma10_cands) == 1
    assert ma10_cands[0].tier == "filtered"


def test_ma_legit_below_current_stays_primary():
    """A real ma20 = $130 on a stock at $140 (legitimate trend pullback
    level) must stay `primary`. Pins floor: the gate must catch
    zero/negative but NOT normal MA values below current price."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma20", 130.0),
    ]
    cands = compute_candidates(facts)
    ma20_cands = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(ma20_cands) == 1
    assert ma20_cands[0].tier == "primary"
