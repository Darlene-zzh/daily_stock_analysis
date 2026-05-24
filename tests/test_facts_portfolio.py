from src.analysis.extractors.portfolio import extract_portfolio_facts


def test_extract_portfolio_facts_held():
    pc = {
        "match_state": "held",
        "holding_shares": 0.7597,
        "avg_cost": 196.18,
        "currency": "USD",
        "unrealized_pnl_pct": 13.33,
        "unrealized_pnl_amount": 14.78,
        "base_currency": "GBP",
        "total_equity": 1200.0,
        "first_buy_date": "2024-08-15",
    }
    facts = extract_portfolio_facts(pc, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "portfolio.holding_shares" in ids
    assert "portfolio.avg_cost" in ids
    assert "portfolio.unrealized_pnl_pct" in ids
    assert "portfolio.unrealized_pnl_amount" in ids
    assert "portfolio.total_equity" in ids
    assert "portfolio.position_match" in ids
    pnl = next(f for f in facts if f.id == "portfolio.unrealized_pnl_pct")
    assert pnl.display_value == "+13.33%"


def test_extract_portfolio_facts_none_match_returns_only_position_match():
    pc = {"match_state": None}
    facts = extract_portfolio_facts(pc, as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "portfolio.position_match" in ids
    assert "portfolio.holding_shares" not in ids


def test_extract_portfolio_facts_empty():
    assert extract_portfolio_facts(None, as_of="2026-05-21T00:43:00Z") == []
