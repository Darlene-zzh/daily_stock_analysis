from src.analysis.facts import FactRecord, FactBundle, CandidateLevel
from src.analysis.prompt_blocks import format_facts_table


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
