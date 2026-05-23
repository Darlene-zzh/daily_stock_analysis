import pytest

from src.notification import _render_action_plan_items as notif_render
from src.services.history_service import _render_action_plan_items as hist_render


def _fact_bundle():
    return {
        "facts": [
            {"id": "technical.resistance", "type": "technical",
             "label": "阻力位", "value": 226.13, "display_value": "$226.13",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"role": "阻力"}},
            {"id": "technical.rsi_12", "type": "technical",
             "label": "RSI(12)", "value": 71.1, "display_value": "71.1",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {"zone": "超买"}},
            {"id": "committee.pm_verdict", "type": "committee",
             "label": "PM 裁决", "value": "hold", "display_value": "Hold",
             "unit": None, "source": "", "confidence": None,
             "as_of": None, "extra": {}},
            {"id": "intel.risk_alert.0", "type": "intel",
             "label": "风险警示", "value": "RSI 71.1 超买",
             "display_value": "RSI 71.1 超买", "unit": None,
             "source": "", "confidence": None, "as_of": None, "extra": {}},
        ],
        "candidates": [],
    }


def _llm_item():
    return {
        "candidate_id": "candidate.exit.1",
        "trigger_price": 226.13,
        "trigger_condition": "阻力位触及",
        "direction": "take_profit",
        "shares": 0.2279,
        "pct_of_position": 30.0,
        "pct_of_equity": 3.5,
        "technical_basis": "RSI 71.1 超买",
        "fundamental_basis": "PM hold (5.8/10)",
        "quant_signal": "风控建议仓位 ≤30%",
        "invalidation_rule": "放量站稳 $230 上方",
        "priority": 1,
        "evidence_refs": ["technical.resistance", "technical.rsi_12",
                          "committee.pm_verdict"],
        "narrative": "RSI 超买 + 阻力位触及 → 减仓",
        "tier": "primary",
        "provenance": "llm",
    }


def _synth_item():
    return {
        "candidate_id": "candidate.stop.1",
        "trigger_price": 213.39,
        "trigger_condition": "MA20 跌破",
        "direction": "stop_loss",
        "shares": 0,
        "pct_of_position": 100.0,
        "technical_basis": "ma20_breakdown（来自代码合成）",
        "evidence_refs": ["technical.ma20", "committee.pm_verdict"],
        "narrative": "MA20 跌破（代码兜底）",
        "tier": "primary",
        "provenance": "synthesized",
        "priority": 2,
    }


def test_notification_render_attaches_superscripts_to_basis_lines():
    lines = notif_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "**触发**：阻力位触及¹" in joined
    assert "**技术面**：RSI 71.1 超买²" in joined
    assert "**量化**：风控建议仓位 ≤30%³" in joined


def test_notification_render_emits_synthesized_badge():
    lines = notif_render([_synth_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "🤖" in joined
    assert "代码兜底" in joined


def test_notification_render_no_badge_for_llm_provenance():
    lines = notif_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "代码兜底" not in joined


def test_notification_render_without_bundle_unchanged():
    """When fact_bundle is None, output must NOT include superscripts or badges
    even if items carry evidence_refs / provenance."""
    lines = notif_render([_llm_item()], fact_bundle=None)
    joined = "\n".join(lines)
    assert "¹" not in joined
    assert "²" not in joined
    assert "代码兜底" not in joined


def test_notification_render_without_evidence_refs_no_superscripts():
    item = _llm_item()
    item.pop("evidence_refs", None)
    lines = notif_render([item], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "¹" not in joined


def test_notification_render_legacy_signature_still_works():
    """Old call sites that pass no fact_bundle keyword must keep working."""
    item = {
        "trigger_price": 100.0, "trigger_condition": "test",
        "direction": "buy", "shares": 1, "priority": 1,
    }
    lines = notif_render([item])
    assert any("100.00" in line for line in lines)


def test_history_render_attaches_superscripts_to_basis_lines():
    lines = hist_render([_llm_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "**触发**：阻力位触及¹" in joined
    assert "**技术面**：RSI 71.1 超买²" in joined
    assert "**量化**：风控建议仓位 ≤30%³" in joined


def test_history_render_emits_synthesized_badge():
    lines = hist_render([_synth_item()], fact_bundle=_fact_bundle())
    joined = "\n".join(lines)
    assert "🤖" in joined
    assert "代码兜底" in joined


def test_history_render_without_bundle_unchanged():
    lines = hist_render([_llm_item()], fact_bundle=None)
    joined = "\n".join(lines)
    assert "¹" not in joined
    assert "代码兜底" not in joined


def test_history_render_legacy_signature_still_works():
    item = {
        "trigger_price": 100.0, "trigger_condition": "test",
        "direction": "buy", "shares": 1, "priority": 1,
    }
    lines = hist_render([item])
    assert any("100.00" in line for line in lines)
