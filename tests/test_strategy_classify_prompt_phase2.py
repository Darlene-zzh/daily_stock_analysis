"""build_strategy_classify_prompt should accept an optional fact_bundle dict
and inject facts table + candidates menu + output contract when present."""
from src.services.portfolio_context_service import build_strategy_classify_prompt


def _bundle_dict():
    return {
        "as_of": "2026-05-21T00:43:00Z",
        "market": "us",
        "stock_code": "NVDA",
        "facts": [
            {"id": "technical.current_price", "type": "technical",
             "label": "现价", "value": 223.47, "display_value": "$223.47",
             "unit": "USD", "source": "yfinance", "confidence": None,
             "as_of": "2026-05-21T00:43:00Z", "extra": {}},
        ],
        "candidates": [
            {"id": "candidate.exit.1", "type": "candidate", "label": "阻力",
             "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": "2026-05-21T00:43:00Z", "extra": {},
             "direction": "take_profit", "price": 226.13,
             "basis_fact_id": "technical.resistance",
             "basis_rule": "resistance_touch",
             "applicable_strategies": ["swing_trade"],
             "tier": "primary", "distance_pct_from_current": 1.2},
        ],
    }


def test_build_prompt_without_bundle_unchanged():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
    )
    assert "[事实数据库]" not in prompt
    assert "[候选触发价位]" not in prompt


def test_build_prompt_with_bundle_injects_three_new_blocks():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
        fact_bundle=_bundle_dict(),
    )
    assert "[事实数据库]" in prompt
    assert "[候选触发价位]" in prompt
    assert "[输出契约 — Phase 2 证据接地]" in prompt
    assert "technical.current_price" in prompt
    assert "candidate.exit.1" in prompt
    # Output JSON template must mention the new fields
    assert "candidate_id" in prompt
    assert "evidence_refs" in prompt


def test_build_prompt_with_empty_bundle_still_safe():
    prompt = build_strategy_classify_prompt(
        portfolio_context_block=None,
        sentiment_dimensions=None,
        compact_dashboard={"stock_code": "NVDA"},
        fact_bundle={"as_of": "x", "market": "us", "stock_code": "NVDA",
                     "facts": [], "candidates": []},
    )
    assert "[事实数据库]" in prompt
    assert "（无可用事实）" in prompt
    assert "（无可用候选）" in prompt
