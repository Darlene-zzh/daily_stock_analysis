from src.analysis.extractors.flow import extract_flow_facts


def test_extract_flow_facts_a_share():
    flow = {
        "status": "ok",
        "stock_flow": {"main_net_inflow": 12345678.0, "inflow_5d": 56789012.0, "inflow_10d": 78901234.0},
        "sector_rankings": {"top": [{"name": "半导体", "flow": 2e9}], "bottom": []},
    }
    facts = extract_flow_facts(flow, market="a", as_of="2026-05-21T00:43:00Z")
    ids = {f.id for f in facts}
    assert "flow.main_net_inflow" in ids
    assert "flow.inflow_5d" in ids
    assert "flow.inflow_10d" in ids


def test_extract_flow_facts_us_returns_empty():
    flow = {"status": "ok", "stock_flow": {"main_net_inflow": 1.0}}
    assert extract_flow_facts(flow, market="us", as_of="2026-05-21T00:43:00Z") == []


def test_extract_flow_facts_not_supported_status():
    flow = {"status": "not_supported"}
    assert extract_flow_facts(flow, market="a", as_of="2026-05-21T00:43:00Z") == []


def test_extract_flow_facts_empty():
    assert extract_flow_facts(None, market="a", as_of="2026-05-21T00:43:00Z") == []
