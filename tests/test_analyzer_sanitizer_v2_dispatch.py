"""When fact_bundle is on result.dashboard, _sanitize_action_plan_items must
route through sanitizer_v2 instead of the legacy cost-basis path."""
from src.analyzer import GeminiAnalyzer


def _bundle_dict_with_candidate():
    return {
        "as_of": "x", "market": "us", "stock_code": "NVDA",
        "facts": [
            {"id": "technical.current_price", "type": "technical", "label": "现价",
             "value": 223.47, "display_value": "$223.47", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
            {"id": "technical.resistance", "type": "technical", "label": "阻力",
             "value": 226.13, "display_value": "$226.13", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
        ],
        "candidates": [
            {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
             "value": 226.13, "display_value": "$226.13", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {},
             "direction": "take_profit", "price": 226.13,
             "basis_fact_id": "technical.resistance",
             "basis_rule": "resistance_touch",
             "applicable_strategies": ["swing_trade"],
             "tier": "primary", "distance_pct_from_current": 1.2},
        ],
    }


def test_sanitizer_routes_to_v2_when_bundle_present():
    """Item with unknown candidate_id is dropped — proof v2 ran."""
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    agent._fact_bundle_for_sanitize = _bundle_dict_with_candidate()
    agent._current_price_for_sanitize = 223.47
    items = [
        {"candidate_id": "candidate.exit.1", "trigger_price": 226.13,
         "direction": "take_profit", "priority": 1,
         "evidence_refs": ["technical.resistance"], "tier": "primary"},
        {"candidate_id": "candidate.exit.FAKE", "trigger_price": 999.99,
         "direction": "take_profit", "priority": 2,
         "evidence_refs": ["a", "b"], "tier": "primary"},
    ]
    out = GeminiAnalyzer._sanitize_action_plan_items(
        agent, items, portfolio_context_block=None, code="NVDA",
        strategy="swing_trade",
    )
    cids = [it.get("candidate_id") for it in out]
    assert "candidate.exit.1" in cids
    assert "candidate.exit.FAKE" not in cids


def test_sanitizer_falls_back_to_legacy_without_bundle():
    """Without a bundle attached, behavior is the legacy cost-basis path."""
    agent = GeminiAnalyzer.__new__(GeminiAnalyzer)
    agent._fact_bundle_for_sanitize = None
    agent._current_price_for_sanitize = None
    items = [
        {"trigger_price": 100.0, "trigger_condition": "x",
         "direction": "take_profit", "priority": 1},
    ]
    out = GeminiAnalyzer._sanitize_action_plan_items(
        agent, items, portfolio_context_block=None, code="NVDA",
        strategy="swing_trade",
    )
    # Legacy passes item through (no avg_cost in block, no rejection)
    assert len(out) == 1
