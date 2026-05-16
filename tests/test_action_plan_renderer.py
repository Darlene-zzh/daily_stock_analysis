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


def _make_result(action_plan_items=None, portfolio_match="held", include_battle=False) -> AnalysisResult:
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
    if include_battle:
        dashboard["battle_plan"] = {
            "sniper_points": {
                "ideal_buy": "420.0",
                "secondary_buy": "415.0",
                "stop_loss": "405.0",
                "take_profit": "445.0",
            },
            "position_strategy": {
                "suggested_position": "降仓防守",
                "entry_plan": "可观察，不追高。",
                "risk_control": "止损参考 405.0",
            },
        }
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


class BattlePlanLabelSwitchTestCase(unittest.TestCase):
    """When the user already holds the stock, the battle_plan strategy line
    should read 调仓策略 instead of 建仓策略.
    """

    def test_history_service_uses_tiao_cang_when_held(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(portfolio_match="held", include_battle=True)
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("调仓策略", md)
        self.assertNotIn("- 建仓策略:", md)

    def test_history_service_keeps_jian_cang_when_not_held(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(portfolio_match="not_held", include_battle=True)
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("建仓策略", md)
        self.assertNotIn("调仓策略", md)

    def test_notification_uses_tiao_cang_when_held(self) -> None:
        result = _make_result(portfolio_match="held", include_battle=True)
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("调仓策略", md)
        self.assertNotIn("- 建仓策略:", md)

    def test_notification_keeps_jian_cang_when_not_held(self) -> None:
        result = _make_result(portfolio_match="not_held", include_battle=True)
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("建仓策略", md)
        self.assertNotIn("调仓策略", md)


class BattlePlanHintLineTestCase(unittest.TestCase):
    """When action_plan_items is present, the 作战计划 block should label itself
    as a quick-glance summary so the reader knows the playbook is above.
    """

    def test_history_service_adds_hint_when_action_plan_present(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(
            action_plan_items=_SAMPLE_ACTION_ITEMS,
            portfolio_match="held",
            include_battle=True,
        )
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("关键点位速查", md)

    def test_history_service_no_hint_without_action_plan(self) -> None:
        svc = HistoryService.__new__(HistoryService)
        result = _make_result(action_plan_items=None, portfolio_match="held", include_battle=True)
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertNotIn("关键点位速查", md)

    def test_notification_adds_hint_when_action_plan_present(self) -> None:
        result = _make_result(
            action_plan_items=_SAMPLE_ACTION_ITEMS,
            portfolio_match="held",
            include_battle=True,
        )
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("关键点位速查", md)

    def test_notification_no_hint_without_action_plan(self) -> None:
        result = _make_result(action_plan_items=None, portfolio_match="held", include_battle=True)
        md = NotificationService().generate_dashboard_report([result])
        self.assertNotIn("关键点位速查", md)


class StrategyAndSentimentRendererTestCase(unittest.TestCase):
    def _result_with_strategy(self):
        dashboard = {
            "core_conclusion": {
                "one_sentence": "短线偏弱",
                "signal_type": "🟡",
                "time_sensitivity": "本周内",
                "position_advice": {"no_position": "x", "has_position": "y"},
                "strategy_choices": [
                    {"id": "stepped_profit_taking", "label_zh": "阶梯式止盈",
                     "emoji": "🪜", "applicable": True,
                     "fit_condition": "已有浮盈", "key_params": "$236/$245",
                     "time_horizon": "滚动"},
                    {"id": "swing_trade", "label_zh": "短线波段",
                     "emoji": "⚡", "applicable": False,
                     "inapplicable_reason": "已有浮盈，不该频繁进出"},
                ],
                "recommended_strategy": "stepped_profit_taking",
                "strategy_thesis": "NVDA 目前结构健康，建议阶梯式止盈兑现。",
                "action_plan_items": [
                    {"trigger_price": 236.5, "direction": "take_profit",
                     "shares": 0.25, "pct_of_position": 33,
                     "pct_of_equity": 2.35, "priority": 1,
                     "trigger_condition": "突破 236"},
                ],
                "position_outcome_summary": {
                    "remaining_shares_after_all_triggers": 0.0,
                    "worst_case_loss_amount": -12.0,
                    "worst_case_currency": "GBP",
                    "best_case_gain_amount": 36.0,
                    "risk_reward_ratio": "1:3",
                },
            },
            "intelligence": {
                "sentiment_dimensions": {
                    "x_twitter": {"buzz_score": 89.0, "buzz_trend": "falling"},
                    "news": {"buzz_score": 61.6, "sentiment_score": 0.48},
                },
            },
        }
        return AnalysisResult(
            code="NVDA", name="NVIDIA", sentiment_score=50,
            trend_prediction="震荡", operation_advice="持有",
            analysis_summary="", report_language="zh",
            dashboard=dashboard, portfolio_match="held",
        )

    def test_notification_renders_strategy_selector(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("策略选择", md)
        self.assertIn("阶梯式止盈", md)
        self.assertIn("已有浮盈，不该频繁进出", md)  # inapplicable_reason
        self.assertIn("策略论述", md)

    def test_notification_renders_sentiment_panel(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("市场情绪", md)
        self.assertIn("89", md)  # x_twitter buzz

    def test_notification_renders_position_outcome(self):
        result = self._result_with_strategy()
        md = NotificationService().generate_dashboard_report([result])
        self.assertIn("仓位流水汇总", md)
        self.assertIn("1:3", md)

    def test_history_service_renders_strategy_selector(self):
        svc = HistoryService.__new__(HistoryService)
        result = self._result_with_strategy()
        md = svc._generate_single_stock_markdown(result, _fake_record())
        self.assertIn("策略选择", md)
        self.assertIn("阶梯式止盈", md)


if __name__ == "__main__":
    unittest.main()
