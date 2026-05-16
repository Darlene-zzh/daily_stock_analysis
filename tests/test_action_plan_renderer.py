"""Tests for action_plan_items rendering in both markdown renderers."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import AnalysisResult
from src.notification import NotificationService
from src.services.history_service import HistoryService


_SAMPLE_ACTION_ITEMS = [
    {
        "trigger_price": 421.0,
        "trigger_condition": "$421 区间回踩 MA5 后企稳 2 日",
        "direction": "sell",
        "shares": 30,
        "pct_of_position": 20.0,
        "pct_of_equity": 3.5,
        "technical_basis": "RSI=74 超买，MA20 压力",
        "fundamental_basis": "诉讼风险尚未 price-in",
        "quant_signal": "量比 1.8，主力净流出",
        "invalidation_rule": "放量站稳 $428 作废",
        "priority": 1,
    },
    {
        "trigger_price": 405.0,
        "trigger_condition": "收盘有效跌破 $405",
        "direction": "stop_loss",
        "shares": 150,
        "pct_of_position": 100.0,
        "pct_of_equity": 17.5,
        "technical_basis": "跌破 MA20 + MA200 双重支撑",
        "fundamental_basis": "消费者信心数据持续下滑",
        "quant_signal": "连续 3 日主力净流出，筹码松动",
        "invalidation_rule": "当日收盘收回 $407 则暂缓",
        "priority": 2,
    },
]


def _make_result(action_plan_items=None, portfolio_match="held") -> AnalysisResult:
    dashboard = {
        "core_conclusion": {
            "one_sentence": "短线回调风险上升，建议分批减仓。",
            "signal_type": "🟡持有观望",
            "time_sensitivity": "本周内",
            "position_advice": {
                "no_position": "暂不参与。",
                "has_position": "持有观察。",
            },
        },
        "intelligence": {"risk_alerts": []},
    }
    if action_plan_items is not None:
        dashboard["core_conclusion"]["action_plan_items"] = action_plan_items
    r = AnalysisResult(
        code="MCD",
        name="McDonald's",
        sentiment_score=50,
        trend_prediction="震荡",
        operation_advice="持有",
        analysis_summary="短线回调风险上升。",
        report_language="zh",
        dashboard=dashboard,
        portfolio_match=portfolio_match,
    )
    return r


def _fake_record():
    return SimpleNamespace(
        code="MCD",
        name="McDonald's",
        sentiment_score=50,
        trend_prediction="震荡",
        operation_advice="持有",
        analysis_summary="",
        news_content="",
        created_at=datetime(2026, 5, 16, 12, 0, 0),
    )


class NotificationActionPlanRendererTestCase(unittest.TestCase):
    def test_action_plan_items_render_in_notification(self) -> None:
        result = _make_result(action_plan_items=_SAMPLE_ACTION_ITEMS)
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("持仓操作计划", md)
        self.assertIn("⬇️", md)
        self.assertIn("421.00", md)
        self.assertIn("减仓 30 股", md)
        self.assertIn("20.0%", md)
        self.assertIn("3.5%", md)
        self.assertIn("RSI=74", md)
        self.assertIn("诉讼风险", md)
        self.assertIn("主力净流出", md)
        self.assertIn("放量站稳", md)

    def test_stop_loss_uses_correct_emoji(self) -> None:
        result = _make_result(action_plan_items=_SAMPLE_ACTION_ITEMS)
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("🛑", md)

    def test_fallback_to_position_advice_when_no_action_plan(self) -> None:
        result = _make_result(action_plan_items=None, portfolio_match=None)
        md = NotificationService().generate_dashboard_report([result])
        self.assertNotIn("持仓操作计划", md)
        self.assertIn("空仓者", md)

    def test_action_plan_items_render_in_history_service(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(action_plan_items=_SAMPLE_ACTION_ITEMS)
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("持仓操作计划", md)
        self.assertIn("⬇️", md)
        self.assertIn("421.00", md)
        self.assertIn("减仓 30 股", md)
        self.assertIn("RSI=74", md)

    def test_history_fallback_to_position_advice_when_no_action_plan(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(action_plan_items=None, portfolio_match=None)
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertNotIn("持仓操作计划", md)
        self.assertIn("空仓者", md)


if __name__ == "__main__":
    unittest.main()
