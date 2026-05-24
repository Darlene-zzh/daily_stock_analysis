from src.analysis.facts import FactRecord, FactBundle, CandidateLevel
from src.analysis.prompt_blocks import format_facts_table, format_candidates_menu


def _bundle_with(facts, candidates=None):
    return FactBundle(
        as_of="2026-05-21T00:43:00Z",
        market="us",
        stock_code="NVDA",
        facts=facts,
        candidates=candidates or [],
    )


def test_format_facts_table_includes_section_header():
    bundle = _bundle_with([
        FactRecord(id="technical.current_price", type="technical",
                   label="现价", value=223.47, display_value="$223.47",
                   source="yfinance", as_of="2026-05-21T00:43:00Z"),
    ])
    out = format_facts_table(bundle)
    assert "## [事实数据库]" in out
    assert "$223.47" in out
    assert "technical.current_price" in out  # fact_id surfaces so LLM can cite


def test_format_facts_table_groups_by_type_in_fixed_order():
    bundle = _bundle_with([
        FactRecord(id="intel.risk_alert.0", type="intel",
                   label="风险警示", value="RSI 71.1 超买", display_value="RSI 71.1 超买"),
        FactRecord(id="technical.ma10", type="technical",
                   label="MA10", value=222.02, display_value="$222.02"),
        FactRecord(id="committee.pm_verdict", type="committee",
                   label="PM 裁决", value="hold", display_value="Hold"),
        FactRecord(id="quant.qlib_rank", type="quant",
                   label="Qlib 截面分位", value=0.85, display_value="前 15%"),
    ])
    out = format_facts_table(bundle)
    # Fixed order: technical → quant → committee → intel → portfolio → flow → chip
    pos_tech = out.index("technical.ma10")
    pos_quant = out.index("quant.qlib_rank")
    pos_committee = out.index("committee.pm_verdict")
    pos_intel = out.index("intel.risk_alert.0")
    assert pos_tech < pos_quant < pos_committee < pos_intel


def test_format_facts_table_empty_bundle_returns_minimal_header():
    bundle = _bundle_with([])
    out = format_facts_table(bundle)
    assert "## [事实数据库]" in out
    assert "（无可用事实）" in out


def _make_candidate(id_, direction, price, basis_rule, strategies, tier="primary",
                    distance=1.0):
    return CandidateLevel(
        id=id_, type="candidate", label=f"{basis_rule}", value=price,
        display_value=f"${price:.2f}", direction=direction, price=price,
        basis_fact_id="technical.resistance", basis_rule=basis_rule,
        applicable_strategies=strategies, tier=tier,
        distance_pct_from_current=distance,
    )


def test_format_candidates_menu_renders_table_with_header():
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.1", "take_profit", 226.13, "resistance_touch",
                        ["swing_trade", "stepped_profit_taking"], distance=1.2),
        _make_candidate("candidate.stop.1", "stop_loss", 213.39, "ma20_breakdown",
                        ["swing_trade", "stepped_profit_taking"], distance=-4.5),
    ])
    out = format_candidates_menu(bundle)
    assert "## [候选触发价位]" in out
    assert "candidate.exit.1" in out
    assert "candidate.stop.1" in out
    assert "$226.13" in out
    assert "resistance_touch" in out
    assert "swing_trade" in out
    assert "禁止创造新价位" in out  # guard against LLM creativity


def test_format_candidates_menu_filters_out_filtered_tier():
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.1", "take_profit", 226.13, "resistance_touch",
                        ["swing_trade"]),
        _make_candidate("candidate.exit.bad", "take_profit", 100.0, "stale_target",
                        ["swing_trade"], tier="filtered"),
    ])
    out = format_candidates_menu(bundle)
    assert "candidate.exit.1" in out
    assert "candidate.exit.bad" not in out


def test_format_candidates_menu_strategy_filter():
    """When recommended_strategy given, candidates that don't apply are excluded
    from the menu so the LLM only chooses from valid options."""
    bundle = _bundle_with([], candidates=[
        _make_candidate("candidate.exit.swing", "take_profit", 226.13, "resistance",
                        ["swing_trade"]),
        _make_candidate("candidate.exit.lth", "take_profit", 280.0, "cost_x_1_5",
                        ["long_term_hold"]),
    ])
    out = format_candidates_menu(bundle, strategy="swing_trade")
    assert "candidate.exit.swing" in out
    assert "candidate.exit.lth" not in out


def test_format_candidates_menu_empty_returns_no_options_note():
    bundle = _bundle_with([], candidates=[])
    out = format_candidates_menu(bundle)
    assert "## [候选触发价位]" in out
    assert "无可用候选" in out


def test_output_contract_zh_constants():
    from src.analysis.prompt_blocks import OUTPUT_CONTRACT_ZH
    assert "candidate_id" in OUTPUT_CONTRACT_ZH
    assert "evidence_refs" in OUTPUT_CONTRACT_ZH
    assert "narrative" in OUTPUT_CONTRACT_ZH
    assert "discipline_anchor" in OUTPUT_CONTRACT_ZH
    assert "至多 1 条" in OUTPUT_CONTRACT_ZH or "at most 1" in OUTPUT_CONTRACT_ZH
    assert "至少 2 个 fact_id" in OUTPUT_CONTRACT_ZH
