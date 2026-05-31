"""Regression guards for ghost-priced candidates.

Motivation: in the NVDA case (2026-05-21 analysis id=13), a stale pre-split
resistance level of $606 was paired with a real current price of ~$140.
``compute_candidates`` happily emitted a take_profit candidate at $606 and
the sanitizer let it through because the original Check #5 only verified
direction polarity, not magnitude. The LLM then anchored its action plan to
$606.

This module pins three pieces of behavior, all currently passing:

1. **Emission preserved** — ghost-priced facts still produce candidates with
   their literal price and faithful ``distance_pct_from_current``. Catches
   regressions where a refactor silently stops emitting the candidate (which
   would mask the data quality problem instead of fixing it).
2. **Ghost gate active** — ``candidate_rules._apply_ghost_gate`` re-tags any
   candidate whose price is non-positive, whose distance exceeds
   ``GHOST_DISTANCE_THRESHOLD_PCT`` (50%), or whose source fact is corrupt
   (``technical.atr_14 <= 0`` or ``>= current``, ``quant.qlib_rank > 1.0``)
   as ``tier='filtered'``. Sanitizer Check #4 then drops items pointing at
   such candidates.
3. **Sanitizer defense-in-depth** — ``sanitizer_v2.sanitize_with_candidates``
   independently refuses items pointing at any candidate whose price is
   non-positive or whose distance exceeds 50%, even if the bundle was
   constructed outside ``compute_candidates`` (manual test fixtures, future
   code paths that synthesize candidates by other means).

History: these tests were originally introduced with the desired-hardening
assertions wrapped in ``pytest.mark.xfail(strict=True)`` so that whoever
implemented the gate would be forced to remove the markers (XPASS under
strict=True breaks the suite). The xfails were flipped to permanent
assertions when the gate landed; see ``repo-nvda-presplit-ghost.md`` for the
superseded hypothesis history.
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
# Ghost gate — now active. These tests originally lived as xfail(strict=True)
# placeholders documenting the desired behavior; the gate lands in
# `candidate_rules._apply_ghost_gate` + `sanitizer_v2._candidate_is_ghost`.
# ---------------------------------------------------------------------------


def test_ghost_resistance_should_be_marked_filtered():
    """A 4x-off resistance must not be `primary` tier (ghost gate active)."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.resistance", 606.0),
    ]
    cands = compute_candidates(facts)
    rt = [c for c in cands if c.basis_rule == "resistance_touch"]
    assert len(rt) == 1
    assert rt[0].tier == "filtered"


def test_ghost_swing_low_should_be_marked_filtered():
    """A stop at 5% of current is a ghost; ghost gate filters it."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.swing_low_20d", 5.0),
    ]
    cands = compute_candidates(facts)
    sl = [c for c in cands if c.basis_rule == "prev_swing_low"]
    assert len(sl) == 1
    assert sl[0].tier == "filtered"


def test_sanitizer_drops_item_pointing_at_ghost_candidate():
    """Even if a primary-tier ghost is constructed manually (test or future
    code path bypassing compute_candidates), sanitizer Check #4.5 refuses
    items pointing at it (defense-in-depth)."""
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
# Ghost gate: any cost-anchor whose |distance_pct_from_current| is
# implausibly large is tagged `tier='filtered'` (now active — see
# `candidate_rules._apply_ghost_gate`).


def test_portfolio_avg_cost_inflated_take_profit_is_recorded_today():
    """A 700x-inflated avg_cost (decimal-shift broker bug) still emits all
    three cost-anchor take_profit candidates at inflated prices — they're
    not silently dropped, just re-tagged ``filtered`` by the ghost gate so
    sanitizer Check #4 drops items pointing at them. Regression guard for
    emission + new tier behavior."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 99999.0, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    cost_anchors = [c for c in cands if c.basis_rule.startswith("cost_plus_")]
    assert len(cost_anchors) == 3  # +5%, +12%, +20%
    assert all(c.price > 100000 for c in cost_anchors)
    assert all(c.tier == "filtered" for c in cost_anchors)


def test_portfolio_avg_cost_tiny_value_stop_loss_is_recorded_today():
    """A 14000x-deflated avg_cost (reverse decimal-shift) emits a sub-cent
    cost_minus_10pct stop_loss — still emitted but ghost-gate flips it to
    ``filtered`` (sub-cent price + distance ~-100% both trip)."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("portfolio.avg_cost", 0.01, type_="portfolio", label="成本均价"),
    ]
    cands = compute_candidates(facts)
    stop_anchors = [c for c in cands if c.basis_rule == "cost_minus_10pct"]
    assert len(stop_anchors) == 1
    assert stop_anchors[0].price < 0.05  # 0.01 * 0.9 = 0.009
    assert stop_anchors[0].tier == "filtered"


def test_portfolio_avg_cost_inflated_should_be_filtered():
    """700x-inflated cost anchors are `filtered` (ghost-gate distance >50%)."""
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


def test_portfolio_avg_cost_tiny_stop_loss_should_be_filtered():
    """A sub-cent stop_loss is a ghost; ghost gate filters it."""
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

def test_qlib_rank_above_one_emits_entry_candidate_today():
    """A corrupt qlib_rank=1.5 still emits a qlib_top_decile_buy entry —
    candidate not silenced — but source-fact ghost check re-tags it
    ``filtered``. Regression guard for the emission pathway."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("quant.qlib_rank", 1.5, type_="quant", label="Qlib 截面分位"),
    ]
    cands = compute_candidates(facts)
    qlib_cands = [c for c in cands if c.basis_rule == "qlib_top_decile_buy"]
    assert len(qlib_cands) == 1
    assert qlib_cands[0].tier == "filtered"


def test_qlib_rank_above_one_should_be_filtered():
    """qlib_rank > 1.0 is corrupt; source-fact ghost gate filters it."""
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

def test_chip_avg_cost_zero_emits_entry_at_zero_today():
    """chip.avg_cost = 0 still emits an entry candidate at price 0 — the
    candidate is not silenced — but ghost gate (price<=0) flips tier."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", 0.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].price == 0.0
    assert chip_cands[0].tier == "filtered"


def test_chip_avg_cost_negative_emits_entry_at_negative_today():
    """chip.avg_cost = -5 emits a negative-priced entry; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", -5.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].price == -5.0
    assert chip_cands[0].tier == "filtered"


def test_chip_avg_cost_zero_should_be_filtered():
    """chip.avg_cost == 0 is corrupt; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("chip.avg_cost", 0.0, type_="chip", label="市场平均成本"),
    ]
    cands = compute_candidates(facts)
    chip_cands = [c for c in cands if c.basis_rule == "chip_avg_cost"]
    assert len(chip_cands) == 1
    assert chip_cands[0].tier == "filtered"


def test_chip_avg_cost_negative_should_be_filtered():
    """Negative chip avg_cost is a sign-flip ghost; gate filters."""
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

def test_support_zero_emits_entry_at_zero_today():
    """support = 0 still emits a support_test entry at 0; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", 0.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].price == 0.0
    assert sup_cands[0].tier == "filtered"


def test_support_negative_emits_entry_at_negative_today():
    """support = -10 emits a negative-priced entry; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", -10.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].price == -10.0
    assert sup_cands[0].tier == "filtered"


def test_support_zero_should_be_filtered():
    """technical.support == 0 is corrupt; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.support", 0.0),
    ]
    cands = compute_candidates(facts)
    sup_cands = [c for c in cands if c.basis_rule == "support_test"]
    assert len(sup_cands) == 1
    assert sup_cands[0].tier == "filtered"


def test_support_negative_should_be_filtered():
    """Negative support is corrupt; ghost gate filters."""
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
# Ghost gate: ATR must be positive AND strictly less than current — anything
# else means the source fact is corrupt and derived candidates are filtered
# (see `_ghost_source_fact_ids` in candidate_rules).


def test_atr_zero_emits_stop_loss_at_current_today():
    """atr_14 = 0 produces an atr_2x stop_loss at exactly `current`; still
    emitted but source-fact ghost check (atr <= 0) re-tags ``filtered``."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 0.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2x) == 1
    assert atr2x[0].price == 140.0
    assert atr2x[0].tier == "filtered"


def test_atr_negative_emits_stop_loss_above_current_today():
    """atr_14 = -50 produces stop_loss = current + 100 = 240 (polarity
    reversed). Still emitted but source-fact ghost check filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", -50.0),
    ]
    cands = compute_candidates(facts)
    atr2x = [c for c in cands if c.basis_rule == "atr_2x_below_current"]
    assert len(atr2x) == 1
    assert atr2x[0].price == 240.0  # > current — polarity reversed
    assert atr2x[0].tier == "filtered"


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


def test_atr_zero_should_be_filtered():
    """ATR == 0: no volatility signal; derived candidates filtered."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", 0.0),
    ]
    cands = compute_candidates(facts)
    atr_cands = [c for c in cands if c.basis_fact_id == "technical.atr_14"]
    assert len(atr_cands) >= 1
    assert all(c.tier == "filtered" for c in atr_cands)


def test_atr_negative_should_be_filtered():
    """Negative ATR = sign-flip; source-fact gate filters derived candidates."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.atr_14", -50.0),
    ]
    cands = compute_candidates(facts)
    atr_cands = [c for c in cands if c.basis_fact_id == "technical.atr_14"]
    assert len(atr_cands) >= 1
    assert all(c.tier == "filtered" for c in atr_cands)


def test_atr_inflated_should_be_filtered():
    """ATR > current is implausible; source-fact gate filters."""
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

def test_ma20_zero_emits_stop_loss_at_zero_today():
    """ma20 = 0 still emits ma20_breakdown stop_loss at $0; ghost gate
    (price <= 0) re-tags ``filtered``."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma20", 0.0),
    ]
    cands = compute_candidates(facts)
    ma20_cands = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(ma20_cands) == 1
    assert ma20_cands[0].price == 0.0
    assert ma20_cands[0].tier == "filtered"


def test_ma10_negative_emits_entry_at_negative_today():
    """ma10 = -5 still emits ma10_pullback entry at -$5; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma10", -5.0),
    ]
    cands = compute_candidates(facts)
    ma10_cands = [c for c in cands if c.basis_rule == "ma10_pullback"]
    assert len(ma10_cands) == 1
    assert ma10_cands[0].price == -5.0
    assert ma10_cands[0].tier == "filtered"


def test_ma20_zero_should_be_filtered():
    """ma20 == 0 is corrupt; ghost gate filters."""
    facts = [
        _fact("technical.current_price", 140.0),
        _fact("technical.ma20", 0.0),
    ]
    cands = compute_candidates(facts)
    ma20_cands = [c for c in cands if c.basis_rule == "ma20_breakdown"]
    assert len(ma20_cands) == 1
    assert ma20_cands[0].tier == "filtered"


def test_ma10_negative_should_be_filtered():
    """Negative ma10 is a sign-flip ghost; gate filters."""
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
