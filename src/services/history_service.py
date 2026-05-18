# -*- coding: utf-8 -*-
"""
===================================
History Query Service Layer
===================================

Responsibilities:
1. Encapsulate history record query logic
2. Provide pagination and filtering functionality
3. Generate detailed reports in Markdown format
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING

from src.config import get_config, resolve_news_window_days
from src.report_language import (
    get_bias_status_emoji,
    get_localized_stock_name,
    get_report_labels,
    get_signal_level,
    localize_bias_status,
    localize_chip_health,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.storage import DatabaseManager
from src.utils.data_processing import normalize_model_used, parse_json_field

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult

logger = logging.getLogger(__name__)


def _render_action_plan_items(items: list) -> list:
    """Render action_plan_items as markdown lines replacing the position-advice table.

    Returns a list of markdown strings ending with a trailing empty string.
    Direction emojis: buy=⬆️ sell=⬇️ stop_loss=🛑 take_profit=🎯
    """
    _DIRECTION_EMOJI = {
        "buy": "⬆️",
        "sell": "⬇️",
        "stop_loss": "🛑",
        "take_profit": "🎯",
    }
    _DIRECTION_ZH = {
        "buy": "买入/加仓",
        "sell": "减仓",
        "stop_loss": "止损清仓",
        "take_profit": "止盈",
    }
    _ORDINALS = ["①", "②", "③", "④", "⑤"]

    lines = ["### 📋 持仓操作计划", ""]
    for idx, item in enumerate(items[:4]):
        direction = item.get("direction", "buy")
        emoji = _DIRECTION_EMOJI.get(direction, "📌")
        direction_zh = _DIRECTION_ZH.get(direction, direction)
        ordinal = _ORDINALS[idx] if idx < len(_ORDINALS) else f"({idx+1})"
        priority = item.get("priority", idx + 1)
        trigger_price = item.get("trigger_price")
        trigger_cond = item.get("trigger_condition", "")
        shares = item.get("shares", 0)
        pct_pos = item.get("pct_of_position")
        pct_eq = item.get("pct_of_equity")
        tech = item.get("technical_basis", "")
        fund = item.get("fundamental_basis", "")
        quant = item.get("quant_signal", "")
        inv_rule = item.get("invalidation_rule", "")

        if not shares or not trigger_price:
            continue

        # position sizing string
        pos_str = ""
        if pct_pos is not None:
            pos_str = f"持仓 {pct_pos:.1f}%"
        if pct_eq:
            pos_str = f"{pos_str} / 权益 {pct_eq:.1f}%" if pos_str else f"权益 {pct_eq:.1f}%"
        ops_str = f"{direction_zh} {shares} 股"
        if pos_str:
            ops_str += f"（{pos_str}）"

        lines.append(f"**{ordinal} {emoji} {direction_zh}**（优先级 {priority}）— 触发价：${trigger_price:.2f}")
        lines.append(f"- **触发**：{trigger_cond}")
        lines.append(f"- **操作**：{ops_str}")
        if tech:
            lines.append(f"- **技术面**：{tech}")
        if fund:
            lines.append(f"- **基本面**：{fund}")
        if quant:
            lines.append(f"- **量化**：{quant}")
        if inv_rule:
            lines.append(f"- **失效**：{inv_rule}")
        lines.append("")
    return lines


_STRATEGY_EMOJI = {
    "long_term_hold": "🌳",
    "swing_trade": "⚡",
    "stepped_profit_taking": "🪜",
    "wait_and_see": "🚪",
}
_STRATEGY_LABEL_ZH = {
    "long_term_hold": "长线持有",
    "swing_trade": "短线波段",
    "stepped_profit_taking": "阶梯式止盈",
    "wait_and_see": "暂不操作",
}


def _render_strategy_section(
    core: dict, labels: dict, report_language: str
) -> list:
    """Render 📌 策略选择 section as markdown lines."""
    choices = core.get("strategy_choices") or []
    recommended = core.get("recommended_strategy")
    thesis = core.get("strategy_thesis")
    if not choices and not recommended and not thesis:
        return []

    lines = [f"### 📌 {labels.get('strategy_section_heading', '策略选择')}", ""]

    if choices:
        lines.extend([
            "| 策略 | 适用条件 | 关键参数 | 时间维度 |",
            "|---|---|---|---|",
        ])
        for c in choices:
            sid = c.get("id") or ""
            emoji = c.get("emoji") or _STRATEGY_EMOJI.get(sid, "📌")
            label = c.get("label_zh") or _STRATEGY_LABEL_ZH.get(sid, sid)
            if not c.get("applicable", True):
                reason = c.get("inapplicable_reason") or "不适用"
                lines.append(f"| {emoji} {label} | ⚪ 不适用（{reason}） |  |  |")
            else:
                fit = c.get("fit_condition") or "—"
                params = c.get("key_params") or "—"
                horizon = c.get("time_horizon") or "—"
                lines.append(f"| {emoji} {label} | {fit} | {params} | {horizon} |")
        lines.append("")

    if recommended:
        emoji = _STRATEGY_EMOJI.get(recommended, "🎯")
        label = _STRATEGY_LABEL_ZH.get(recommended, recommended)
        heading = labels.get("recommended_strategy_heading", "AI 推荐策略")
        lines.append(f"**🎯 {heading}**: {emoji} {label}")
        lines.append("")

    if thesis:
        thesis_heading = labels.get("strategy_thesis_heading", "策略论述")
        lines.append(f"**{thesis_heading}**：")
        lines.append(f"> {thesis}")
        lines.append("")

    return lines


def _render_sentiment_panel(intel: dict, labels: dict) -> list:
    """Render 📱 市场情绪 section as markdown lines."""
    dims = (intel or {}).get("sentiment_dimensions")
    if not isinstance(dims, dict) or not dims:
        return []

    heading = labels.get("sentiment_section_heading", "市场情绪")
    lines = [f"### 📱 {heading}", ""]
    lines.extend(["| 来源 | Buzz | Sentiment | Trend | Mentions |", "|---|---|---|---|---|"])

    source_order = ["news", "reddit", "x_twitter", "polymarket", "stocktwits"]
    source_labels = {
        "news": "📰 News",
        "reddit": "🔴 Reddit",
        "x_twitter": "🐦 X",
        "polymarket": "🔮 Polymarket",
        "stocktwits": "💬 StockTwits",
    }
    for key in source_order:
        d = dims.get(key)
        if not isinstance(d, dict):
            continue
        buzz = d.get("buzz_score")
        sent = d.get("sentiment_score")
        trend = d.get("buzz_trend") or "—"
        mentions = d.get("mentions_7d") or d.get("messages_sampled") or "—"
        if key == "stocktwits":
            bull = d.get("bullish_ratio")
            bear = d.get("bearish_ratio")
            sent = f"Bull {round(bull*100)}% / Bear {round(bear*100)}%" if bull is not None else "—"
            buzz = "—"
            trend = "—"
        lines.append(
            f"| {source_labels[key]} | {buzz if buzz is not None else '—'} "
            f"| {sent if sent is not None else '—'} | {trend} | {mentions} |"
        )
    lines.append("")
    return lines


def _render_position_outcome(outcome: dict, labels: dict) -> list:
    """Render 仓位流水汇总 block."""
    if not isinstance(outcome, dict) or not outcome:
        return []
    heading = labels.get("position_outcome_heading", "仓位流水汇总")
    rr_label = labels.get("rr_ratio_label", "风险回报比")
    remain = outcome.get("remaining_shares_after_all_triggers")
    wl = outcome.get("worst_case_loss_amount")
    wc = outcome.get("worst_case_currency") or ""
    bg = outcome.get("best_case_gain_amount")
    rr = outcome.get("risk_reward_ratio") or "N/A"
    return [
        f"**📊 {heading}**",
        "",
        f"- 执行所有触发后剩余仓位：{remain if remain is not None else '—'} 股",
        f"- 最差止损：{wl if wl is not None else '—'} {wc}",
        f"- 最好止盈：{bg if bg is not None else '—'} {wc}",
        f"- {rr_label}：{rr}",
        "",
    ]


def _render_structured_risk(
    risk_assessment: Optional[dict], report_language: str = "zh"
) -> list:
    """Render the standalone Risk Manager callout (Sprint 4).

    Section ``## 🛡️ 风险评估 / Risk Assessment`` only appears when the
    backend attached a ``risk_assessment`` payload via the Sprint 4
    opt-in.  Mirror of :func:`src.notification._render_structured_risk`;
    the two MUST produce byte-identical output (Sprint 4 invariant).
    """
    if not isinstance(risk_assessment, dict) or not risk_assessment:
        return []
    lang = "en" if str(report_language).lower().startswith("en") else "zh"
    heading = "🛡️ Risk Assessment" if lang == "en" else "🛡️ 风险评估"
    out: List[str] = [f"## {heading}", ""]

    severity = risk_assessment.get("severity") or "—"
    pos_pct = risk_assessment.get("suggested_position_pct")
    tail_risk = risk_assessment.get("tail_risk_score")
    var_5pct = risk_assessment.get("var_estimate_5pct")
    vol = risk_assessment.get("volatility_annualised")
    veto = risk_assessment.get("veto")
    flags = risk_assessment.get("red_flags") or []
    rationale = risk_assessment.get("rationale")

    if lang == "en":
        head = f"**Severity:** `{severity}`"
    else:
        head = f"**严重级别 / Severity**：`{severity}`"
    if pos_pct is not None:
        try:
            head += (
                f" · suggested position {float(pos_pct) * 100:.1f}%"
                if lang == "en"
                else f" · 建议仓位 {float(pos_pct) * 100:.1f}%"
            )
        except (TypeError, ValueError):
            pass
    if veto:
        head += " · veto=true"
    out.append(head)

    metrics: list = []
    if tail_risk is not None:
        try:
            tail_lbl = "Tail-risk score" if lang == "en" else "尾部风险评分"
            metrics.append(f"{tail_lbl}: {float(tail_risk):.2f} / 10")
        except (TypeError, ValueError):
            pass
    if var_5pct is not None:
        try:
            var_lbl = "1-day 5% VaR" if lang == "en" else "1 日 5% VaR"
            metrics.append(f"{var_lbl}: {float(var_5pct) * 100:.2f}%")
        except (TypeError, ValueError):
            pass
    if vol is not None:
        try:
            vol_lbl = "Ann. volatility" if lang == "en" else "年化波动率"
            metrics.append(f"{vol_lbl}: {float(vol) * 100:.1f}%")
        except (TypeError, ValueError):
            pass
    if metrics:
        out.append("")
        for m in metrics:
            out.append(f"- {m}")

    if flags:
        out.append("")
        flag_heading = "Red flags" if lang == "en" else "风险信号"
        out.append(f"**{flag_heading}**")
        for f in flags[:6]:
            out.append(f"- {f}")

    if rationale:
        out.append("")
        out.append(f"> {rationale}")

    out.append("")
    return out


def _render_committee_minutes(
    committee: Optional[dict], labels: dict, report_language: str = "zh"
) -> list:
    """Render the Investment Committee Minutes section as markdown lines.

    Mirror of :func:`src.notification._render_committee_minutes` — both
    renderers must produce structurally identical output so the history
    Markdown matches the push notification.  Per repo memory rule, this
    pair must be kept in sync; structural drift between them is a known
    footgun.

    Returns ``[]`` when ``committee`` is missing / empty.
    """
    if not isinstance(committee, dict) or not committee:
        return []

    try:
        from src.agent.agents.master_personas import PERSONA_DISPLAY
    except Exception:  # pragma: no cover
        PERSONA_DISPLAY = {}

    lang = "en" if str(report_language).lower().startswith("en") else "zh"
    heading_zh = "📋 投委会会议纪要"
    heading_en = "📋 Investment Committee Minutes"
    section_heading = heading_en if lang == "en" else heading_zh

    lines: List[str] = [f"### {section_heading}", ""]

    status = (committee.get("status") or "ok").lower()
    missing_agents = committee.get("missing_agents") or []
    budget_used = committee.get("budget_used")
    budget_cap = committee.get("budget_cap")

    if status == "partial":
        if lang == "en":
            lines.append(
                f"> Status: partial — {len(missing_agents)} agent(s) absent "
                "(committee verdict still issued)."
            )
        else:
            lines.append(
                f"> 状态：部分完成 — 缺席 {len(missing_agents)} 个 agent，"
                "PM 仍出具了结论。"
            )
        lines.append("")
    elif status == "failed":
        if lang == "en":
            lines.append(
                "> Status: inconclusive — treat the committee output as advisory only."
            )
        else:
            lines.append(
                "> 状态：未达成结论 — 仅作辅助参考。"
            )
        lines.append("")

    pm_verdict = committee.get("pm_verdict")
    pm_score = committee.get("pm_score")
    pm_rationale = committee.get("pm_rationale")
    pm_dissents = committee.get("pm_dissents") or []
    if status != "failed" and pm_verdict:
        if lang == "en":
            lines.append(f"**PM verdict:** `{pm_verdict}` (score {pm_score})")
        else:
            lines.append(f"**PM 决议**：`{pm_verdict}`（评分 {pm_score}）")
        if pm_rationale:
            lines.append("")
            lines.append(f"> {pm_rationale}")
        if pm_dissents:
            label = "PM dissents" if lang == "en" else "PM 异议"
            lines.append("")
            lines.append(f"_{label}: {', '.join(pm_dissents)}_")
        lines.append("")

    risk = committee.get("risk")
    if isinstance(risk, dict) and (risk.get("severity") or risk.get("red_flags")):
        severity = risk.get("severity") or "—"
        pos_pct = risk.get("suggested_position_pct")
        veto = risk.get("veto")
        red_flags = risk.get("red_flags") or []
        if lang == "en":
            head = f"**Risk:** severity={severity}"
        else:
            head = f"**风险**：severity={severity}"
        if pos_pct is not None:
            try:
                head += f" · suggested position {float(pos_pct) * 100:.1f}%"
            except (TypeError, ValueError):
                pass
        if veto:
            head += " · veto=true"
        lines.append(head)
        if red_flags:
            for flag in red_flags[:6]:
                lines.append(f"- {flag}")
        lines.append("")

    debate = committee.get("debate") or []
    if debate:
        timeline_heading = "Debate timeline" if lang == "en" else "辩论时间线"
        lines.append(f"**{timeline_heading}**")
        lines.append("")
        rounds = sorted(
            {int(e.get("round_index") or 0) for e in debate if isinstance(e, dict)}
        )
        for r in rounds:
            bull = next(
                (e for e in debate if e.get("round_index") == r and e.get("side") == "bull"),
                None,
            )
            bear = next(
                (e for e in debate if e.get("round_index") == r and e.get("side") == "bear"),
                None,
            )
            bull_claim = (bull or {}).get("claim") or "—"
            bear_claim = (bear or {}).get("claim") or "—"
            lines.append(
                f"- Round {r} — Bull: {bull_claim}; Bear: {bear_claim}"
            )
        lines.append("")

    masters = committee.get("masters") or []
    if masters:
        grid_heading = "Lens views" if lang == "en" else "大师视角"
        lines.append(f"**{grid_heading}**")
        lines.append("")
        for m in masters:
            persona_id = m.get("persona") or "<unknown>"
            display = PERSONA_DISPLAY.get(persona_id, {})
            display_name = display.get("display_en") or persona_id
            verdict = m.get("verdict") or "—"
            score = m.get("score")
            headline = m.get("headline") or ""
            m_status = (m.get("status") or "ok").lower()
            badge = ""
            if m_status != "ok":
                if lang == "en":
                    badge = " _(absent)_"
                else:
                    badge = " _(缺席)_"
            zh_subtitle = ""
            if lang != "en" and display.get("display_zh"):
                zh_subtitle = f"（{display['display_zh']}）"
            lines.append(
                f"- **{display_name}{zh_subtitle}** — `{verdict}` "
                f"(score {score if score is not None else '—'}){badge}"
            )
            if headline and m_status == "ok":
                lines.append(f"  - {headline}")
        lines.append("")

    if budget_used is not None and budget_cap is not None:
        footnote = (
            f"_LLM call budget: {budget_used}/{budget_cap}_"
            if lang == "en"
            else f"_LLM 调用预算：{budget_used}/{budget_cap}_"
        )
        lines.append(footnote)
        lines.append("")

    return lines


class MarkdownReportGenerationError(Exception):
    """Exception raised when Markdown report generation fails due to internal errors."""

    def __init__(self, message: str, record_id: str = None):
        self.message = message
        self.record_id = record_id
        super().__init__(self.message)


class HistoryService:
    """
    History Query Service
    
    Encapsulates query logic for historical analysis records.
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the history query service.
        
        Args:
            db_manager: Database manager (optional, defaults to singleton instance)
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_history_list(
        self,
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get history analysis list.
        
        Args:
            stock_code: Stock code filter
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            page: Page number
            limit: Items per page
            
        Returns:
            Dictionary containing total count and items
        """
        try:
            # Parse date parameters
            start_dt = None
            end_dt = None
            
            if start_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                except ValueError:
                    logger.warning(f"无效的 start_date 格式: {start_date}")
            
            if end_date:
                try:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError:
                    logger.warning(f"无效的 end_date 格式: {end_date}")
            
            # Calculate offset
            offset = (page - 1) * limit
            
            # Use new paginated query method
            records, total = self.db.get_analysis_history_paginated(
                code=stock_code,
                start_date=start_dt,
                end_date=end_dt,
                offset=offset,
                limit=limit
            )
            
            # Convert to response format
            items = []
            for record in records:
                items.append({
                    "id": record.id,
                    "query_id": record.query_id,
                    "stock_code": record.code,
                    "stock_name": record.name,
                    "report_type": record.report_type,
                    "sentiment_score": record.sentiment_score,
                    "operation_advice": record.operation_advice,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                })
            
            return {
                "total": total,
                "items": items,
            }
            
        except Exception as e:
            logger.error(f"查询历史列表失败: {e}", exc_info=True)
            return {"total": 0, "items": []}

    def _resolve_record(self, record_id: str):
        """
        Resolve a record_id parameter to an AnalysisHistory object.

        Tries integer primary key first; falls back to query_id string lookup
        when the value is not a valid integer.

        Args:
            record_id: integer PK (as string) or query_id string

        Returns:
            AnalysisHistory object or None
        """
        try:
            int_id = int(record_id)
            record = self.db.get_analysis_history_by_id(int_id)
            if record:
                return record
        except (ValueError, TypeError):
            pass
        # Fall back to query_id lookup
        return self.db.get_latest_analysis_by_query_id(record_id)

    def resolve_and_get_detail(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolve record_id (int PK or query_id string) and return history detail.

        Args:
            record_id: integer PK (as string) or query_id string

        Returns:
            Complete analysis report dict, or None
        """
        try:
            record = self._resolve_record(record_id)
            if not record:
                return None
            return self._record_to_detail_dict(record)
        except Exception as e:
            logger.error(f"resolve_and_get_detail failed for {record_id}: {e}", exc_info=True)
            return None

    def resolve_and_get_news(self, record_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """
        Resolve record_id (int PK or query_id string) and return associated news.

        Args:
            record_id: integer PK (as string) or query_id string
            limit: max items to return

        Returns:
            List of news intel dicts
        """
        try:
            record = self._resolve_record(record_id)
            if not record:
                logger.warning(f"resolve_and_get_news: record not found for {record_id}")
                return []
            return self.get_news_intel(query_id=record.query_id, limit=limit)
        except Exception as e:
            logger.error(f"resolve_and_get_news failed for {record_id}: {e}", exc_info=True)
            return []

    def get_history_detail_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """
        Get history report detail.

        Uses database primary key for precise query, avoiding returning incorrect records 
        due to duplicate query_id in batch analysis.

        Args:
            record_id: Analysis history record primary key ID

        Returns:
            Complete analysis report dictionary, or None if not exists
        """
        try:
            record = self.db.get_analysis_history_by_id(record_id)
            if not record:
                return None
            return self._record_to_detail_dict(record)
        except Exception as e:
            logger.error(f"根据 ID 查询历史详情失败: {e}", exc_info=True)
            return None

    @staticmethod
    def _normalize_display_sniper_value(value: Any) -> Optional[str]:
        """Normalize sniper point values for history display."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text in {"-", "—", "N/A"}:
            return None
        return text

    def _get_display_sniper_points(self, record, raw_result: Any) -> Dict[str, Optional[str]]:
        """Prefer raw dashboard sniper strings for history display, then fall back to numeric DB columns."""
        raw_points: Dict[str, Any] = {}
        if isinstance(raw_result, dict):
            for candidate in (raw_result.get("dashboard"), raw_result):
                if not isinstance(candidate, dict):
                    continue
                raw_points = DatabaseManager._find_sniper_in_dashboard(candidate) or raw_points
                if any(raw_points.get(k) is not None for k in ("ideal_buy", "secondary_buy", "stop_loss", "take_profit")):
                    break

        display_points: Dict[str, Optional[str]] = {}
        for field in ("ideal_buy", "secondary_buy", "stop_loss", "take_profit"):
            raw_value = self._normalize_display_sniper_value(raw_points.get(field))
            if raw_value is not None:
                display_points[field] = raw_value
                continue
            db_value = getattr(record, field, None)
            display_points[field] = str(db_value) if db_value is not None else None
        return display_points

    def _record_to_detail_dict(self, record) -> Dict[str, Any]:
        """
        Convert an AnalysisHistory ORM record to a detail response dict.
        """
        raw_result = parse_json_field(record.raw_result)

        model_used = (raw_result or {}).get("model_used") if isinstance(raw_result, dict) else None
        model_used = normalize_model_used(model_used)
        sniper_points = self._get_display_sniper_points(record, raw_result)

        context_snapshot = None
        if record.context_snapshot:
            try:
                context_snapshot = json.loads(record.context_snapshot)
            except json.JSONDecodeError:
                context_snapshot = record.context_snapshot

        return {
            "id": record.id,
            "query_id": record.query_id,
            "stock_code": record.code,
            "stock_name": record.name,
            "report_type": record.report_type,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "model_used": model_used,
            "analysis_summary": record.analysis_summary,
            "operation_advice": record.operation_advice,
            "trend_prediction": record.trend_prediction,
            "sentiment_score": record.sentiment_score,
            "sentiment_label": self._get_sentiment_label(record.sentiment_score or 50),
            "ideal_buy": sniper_points.get("ideal_buy"),
            "secondary_buy": sniper_points.get("secondary_buy"),
            "stop_loss": sniper_points.get("stop_loss"),
            "take_profit": sniper_points.get("take_profit"),
            "news_content": record.news_content,
            "raw_result": raw_result,
            "context_snapshot": context_snapshot,
        }

    def delete_history_records(self, record_ids: List[int]) -> int:
        """
        Delete specified analysis history records.

        Args:
            record_ids: List of history record primary key IDs

        Returns:
            Number of records actually deleted

        Raises:
            Exception: Re-raises any storage-layer exception so the API caller
                       receives a proper 500 error instead of a silent success.
        """
        return self.db.delete_analysis_history_records(record_ids)

    def get_news_intel(self, query_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """
        Get news intelligence associated with a specified query_id.

        Args:
            query_id: Unique analysis identifier
            limit: Result limit

        Returns:
            List of news intelligence (containing title, snippet, and url)
        """
        try:
            records = self.db.get_news_intel_by_query_id(query_id=query_id, limit=limit)

            if not records:
                records = self._fallback_news_by_analysis_context(query_id=query_id, limit=limit)

            items: List[Dict[str, str]] = []
            for record in records:
                snippet = (record.snippet or "").strip()
                if len(snippet) > 200:
                    snippet = f"{snippet[:197]}..."
                items.append({
                    "title": record.title,
                    "snippet": snippet,
                    "url": record.url,
                })

            return items

        except Exception as e:
            logger.error(f"查询新闻情报失败: {e}", exc_info=True)
            return []

    def get_news_intel_by_record_id(self, record_id: int, limit: int = 20) -> List[Dict[str, str]]:
        """
        Get associated news intelligence based on analysis history record ID.

        Parses record_id to query_id, then calls get_news_intel.

        Args:
            record_id: Analysis history primary key ID
            limit: Result limit

        Returns:
            List of news intelligence (containing title, snippet, and url)
        """
        try:
            # Look up the corresponding AnalysisHistory record by record_id
            record = self.db.get_analysis_history_by_id(record_id)
            if not record:
                logger.warning(f"No analysis record found for record_id={record_id}")
                return []

            # Get query_id from record, then call original method
            return self.get_news_intel(query_id=record.query_id, limit=limit)

        except Exception as e:
            logger.error(f"根据 record_id 查询新闻情报失败: {e}", exc_info=True)
            return []

    def _fallback_news_by_analysis_context(self, query_id: str, limit: int) -> List[Any]:
        """
        Fallback by analysis context when direct query_id lookup returns no news.

        Typical scenarios:
        - URL-level dedup keeps one canonical news row across repeated analyses.
        - Legacy records may have different historical query_id strategies.
        """
        records = self.db.get_analysis_history(query_id=query_id, limit=1)
        if not records:
            return []

        analysis = records[0]
        if not analysis.code or not analysis.created_at:
            return []

        # Narrow down to same-stock recent news, then filter by analysis time window.
        days = max(1, (datetime.now() - analysis.created_at).days + 1)
        candidates = self.db.get_recent_news(code=analysis.code, days=days, limit=max(limit * 5, 50))

        start_time = analysis.created_at - timedelta(hours=6)
        end_time = analysis.created_at + timedelta(hours=6)
        matched = [
            item for item in candidates
            if item.fetched_at and start_time <= item.fetched_at <= end_time
        ]

        # 历史兜底链路也做发布时间硬过滤，避免旧库脏数据重新冒出。
        cfg = get_config()
        window_days = resolve_news_window_days(
            news_max_age_days=getattr(cfg, "news_max_age_days", 3),
            news_strategy_profile=getattr(cfg, "news_strategy_profile", "short"),
        )
        # Anchor to analysis date instead of "today" to preserve historical context.
        anchor_date = analysis.created_at.date()
        latest_allowed = anchor_date + timedelta(days=1)
        earliest_allowed = anchor_date - timedelta(days=max(0, window_days - 1))

        filtered = []
        for item in matched:
            if not item.published_date:
                continue
            if isinstance(item.published_date, datetime):
                published = item.published_date.date()
            elif isinstance(item.published_date, date):
                published = item.published_date
            else:
                continue
            if earliest_allowed <= published <= latest_allowed:
                filtered.append(item)

        return filtered[:limit]
    
    def _get_sentiment_label(self, score: int) -> str:
        """
        Get sentiment label based on score.

        Args:
            score: Sentiment score (0-100)

        Returns:
            Sentiment label
        """
        if score >= 80:
            return "极度乐观"
        elif score >= 60:
            return "乐观"
        elif score >= 40:
            return "中性"
        elif score >= 20:
            return "悲观"
        else:
            return "极度悲观"

    def get_markdown_report(self, record_id: str) -> Optional[str]:
        """
        Generate a Markdown report for a single analysis history record.

        This method reconstructs an AnalysisResult from the stored raw_result
        and generates a detailed Markdown report similar to the push notifications.

        Args:
            record_id: integer PK (as string) or query_id string

        Returns:
            Markdown formatted report string, or None if record not found

        Raises:
            MarkdownReportGenerationError: If report generation fails due to internal errors
        """
        record = self._resolve_record(record_id)
        if not record:
            logger.warning(f"get_markdown_report: record not found for {record_id}")
            return None

        # Rebuild AnalysisResult from raw_result
        raw_result = parse_json_field(record.raw_result)
        if not raw_result:
            logger.error(f"get_markdown_report: raw_result is empty for {record_id}")
            raise MarkdownReportGenerationError(
                f"raw_result is empty or invalid for record {record_id}",
                record_id=record_id
            )

        try:
            result = self._rebuild_analysis_result(raw_result, record)
        except Exception as e:
            logger.error(f"get_markdown_report: failed to rebuild AnalysisResult for {record_id}: {e}", exc_info=True)
            raise MarkdownReportGenerationError(
                f"Failed to rebuild AnalysisResult: {str(e)}",
                record_id=record_id
            ) from e

        if not result:
            logger.error(f"get_markdown_report: _rebuild_analysis_result returned None for {record_id}")
            raise MarkdownReportGenerationError(
                f"Failed to rebuild AnalysisResult from raw_result",
                record_id=record_id
            )

        # Generate Markdown report
        try:
            return self._generate_single_stock_markdown(result, record)
        except Exception as e:
            logger.error(f"get_markdown_report: failed to generate markdown for {record_id}: {e}", exc_info=True)
            raise MarkdownReportGenerationError(
                f"Failed to generate markdown report: {str(e)}",
                record_id=record_id
            ) from e

    def _rebuild_analysis_result(
        self,
        raw_result: Dict[str, Any],
        record
    ) -> Optional[AnalysisResult]:
        """
        Rebuild an AnalysisResult object from stored raw_result dict.

        Args:
            raw_result: The parsed raw_result JSON dict
            record: The AnalysisHistory ORM record

        Returns:
            AnalysisResult object or None
        """
        try:
            from src.analyzer import AnalysisResult
            # Extract dashboard data if available
            dashboard = raw_result.get("dashboard", {})

            # Build AnalysisResult with available data
            return AnalysisResult(
                code=raw_result.get("code", record.code),
                name=raw_result.get("name", record.name),
                sentiment_score=raw_result.get("sentiment_score", record.sentiment_score or 50),
                trend_prediction=raw_result.get("trend_prediction", record.trend_prediction or ""),
                operation_advice=raw_result.get("operation_advice", record.operation_advice or ""),
                decision_type=raw_result.get("decision_type", "hold"),
                confidence_level=raw_result.get("confidence_level", "中"),
                report_language=normalize_report_language(raw_result.get("report_language")),
                dashboard=dashboard,
                trend_analysis=raw_result.get("trend_analysis", ""),
                short_term_outlook=raw_result.get("short_term_outlook", ""),
                medium_term_outlook=raw_result.get("medium_term_outlook", ""),
                technical_analysis=raw_result.get("technical_analysis", ""),
                ma_analysis=raw_result.get("ma_analysis", ""),
                volume_analysis=raw_result.get("volume_analysis", ""),
                pattern_analysis=raw_result.get("pattern_analysis", ""),
                fundamental_analysis=raw_result.get("fundamental_analysis", ""),
                sector_position=raw_result.get("sector_position", ""),
                company_highlights=raw_result.get("company_highlights", ""),
                news_summary=raw_result.get("news_summary", record.news_content or ""),
                market_sentiment=raw_result.get("market_sentiment", ""),
                hot_topics=raw_result.get("hot_topics", ""),
                analysis_summary=raw_result.get("analysis_summary", record.analysis_summary or ""),
                key_points=raw_result.get("key_points", ""),
                risk_warning=raw_result.get("risk_warning", ""),
                buy_reason=raw_result.get("buy_reason", ""),
                market_snapshot=raw_result.get("market_snapshot"),
                search_performed=raw_result.get("search_performed", False),
                data_sources=raw_result.get("data_sources", ""),
                success=raw_result.get("success", True),
                error_message=raw_result.get("error_message"),
                current_price=raw_result.get("current_price"),
                change_pct=raw_result.get("change_pct"),
                model_used=raw_result.get("model_used"),
                portfolio_match=raw_result.get("portfolio_match"),
            )
        except Exception as e:
            logger.error(f"Failed to rebuild AnalysisResult: {e}", exc_info=True)
            return None

    def _generate_single_stock_markdown(
        self,
        result: AnalysisResult,
        record
    ) -> str:
        """
        Generate a Markdown report for a single stock analysis.

        This follows the same format as NotificationService.generate_dashboard_report()
        using dashboard structured data for detailed report.

        Args:
            result: The AnalysisResult object
            record: The AnalysisHistory ORM record

        Returns:
            Markdown formatted report string
        """
        report_date = record.created_at.strftime("%Y-%m-%d") if record.created_at else datetime.now().strftime("%Y-%m-%d")
        report_time = record.created_at.strftime("%H:%M:%S") if record.created_at else datetime.now().strftime("%H:%M:%S")
        report_language = normalize_report_language(getattr(result, "report_language", "zh"))
        labels = get_report_labels(report_language)
        analysis_date_label = "Analysis Date" if report_language == "en" else "分析日期"
        report_time_label = "Report Time" if report_language == "en" else "报告生成时间"
        reason_label = "Rationale" if report_language == "en" else "操作理由"
        risk_warning_label = "Risk Warning" if report_language == "en" else "风险提示"
        technical_heading = "Technicals" if report_language == "en" else "技术面"
        ma_label = "Moving Averages" if report_language == "en" else "均线"
        volume_analysis_label = "Volume" if report_language == "en" else "量能"
        news_heading = "News Flow" if report_language == "en" else "消息面"

        # Escape markdown special characters in stock name
        name_escaped = self._escape_md(
            get_localized_stock_name(result.name, result.code, report_language)
        ) or result.code

        # Get signal level
        signal_text, signal_emoji, signal_tag = self._get_signal_level(result)
        dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}

        report_lines = [
            f"# 📊 {name_escaped} ({result.code}) {labels['report_title']}",
            "",
            f"> {analysis_date_label}: **{report_date}** | {report_time_label}: {report_time}",
            "",
            "---",
            "",
        ]

        # ========== 舆情与基本面概览（放在最前面）==========
        intel = dashboard.get('intelligence', {}) if dashboard else {}
        if intel:
            report_lines.extend([
                f"### 📰 {labels['info_heading']}",
                "",
            ])

            def _zh_for(idx, zh_list):
                if not isinstance(zh_list, list) or idx >= len(zh_list):
                    return ""
                val = zh_list[idx]
                return val.strip() if isinstance(val, str) else ""

            def _zh_scalar(value):
                return value.strip() if isinstance(value, str) else ""

            # 舆情情绪总结
            if intel.get('sentiment_summary'):
                report_lines.append(f"**💭 {labels['sentiment_summary_label']}**: {intel['sentiment_summary']}")
                zh = _zh_scalar(intel.get('sentiment_summary_zh'))
                if zh:
                    report_lines.append(f"{zh}")
            # 业绩预期
            if intel.get('earnings_outlook'):
                report_lines.append(f"**📊 {labels['earnings_outlook_label']}**: {intel['earnings_outlook']}")
                zh = _zh_scalar(intel.get('earnings_outlook_zh'))
                if zh:
                    report_lines.append(f"{zh}")
            # 风险警报（醒目显示）
            risk_alerts = intel.get('risk_alerts', [])
            risk_alerts_zh = intel.get('risk_alerts_zh', [])
            if risk_alerts:
                report_lines.append("")
                report_lines.append(f"**🚨 {labels['risk_alerts_label']}**:")
                for i, alert in enumerate(risk_alerts):
                    report_lines.append(f"- {alert}")
                    zh = _zh_for(i, risk_alerts_zh)
                    if zh:
                        report_lines.append(f"  {zh}")
            # 利好催化
            catalysts = intel.get('positive_catalysts', [])
            catalysts_zh = intel.get('positive_catalysts_zh', [])
            if catalysts:
                report_lines.append("")
                report_lines.append(f"**✨ {labels['positive_catalysts_label']}**:")
                for i, cat in enumerate(catalysts):
                    report_lines.append(f"- {cat}")
                    zh = _zh_for(i, catalysts_zh)
                    if zh:
                        report_lines.append(f"  {zh}")
            # 最新消息
            if intel.get('latest_news'):
                report_lines.append("")
                report_lines.append(f"**📢 {labels['latest_news_label']}**: {intel['latest_news']}")
                zh = _zh_scalar(intel.get('latest_news_zh'))
                if zh:
                    report_lines.append(f"{zh}")
            report_lines.append("")

        # ========== 📱 市场情绪 ==========
        report_lines.extend(_render_sentiment_panel(intel, labels))

        # ========== 核心结论 ==========
        core = dashboard.get('core_conclusion', {}) if dashboard else {}
        one_sentence = core.get('one_sentence', result.analysis_summary)
        time_sense = core.get('time_sensitivity', labels['default_time_sensitivity'])
        pos_advice = core.get('position_advice', {})

        report_lines.extend([
            f"### 📌 {labels['core_conclusion_heading']}",
            "",
            f"**{signal_emoji} {signal_text}** | {localize_trend_prediction(result.trend_prediction, report_language)}",
            "",
            f"> **{labels['one_sentence_label']}**: {one_sentence}",
            "",
            f"⏰ **{labels['time_sensitivity_label']}**: {time_sense}",
            "",
        ])
        # 持仓操作计划（action_plan_items 优先；fallback 到 position_advice 表格）
        action_plan_items = (
            core.get("action_plan_items") if isinstance(core.get("action_plan_items"), list)
            else None
        )
        if action_plan_items:
            report_lines.extend(_render_action_plan_items(action_plan_items))
        elif pos_advice:
            match = getattr(result, "portfolio_match", None)
            no_pos_text = pos_advice.get(
                "no_position",
                localize_operation_advice(result.operation_advice, report_language),
            )
            has_pos_text = pos_advice.get(
                "has_position",
                labels["continue_holding"],
            )
            header = [
                f"| {labels['position_status_label']} | {labels['action_advice_label']} |",
                "|---------|---------|",
            ]
            if match == "held":
                body = [f"| 💼 **{labels['has_position_label']}** | {has_pos_text} |"]
            elif match == "not_held":
                body = [f"| 🆕 **{labels['no_position_label']}** | {no_pos_text} |"]
            else:
                body = [
                    f"| 🆕 **{labels['no_position_label']}** | {no_pos_text} |",
                    f"| 💼 **{labels['has_position_label']}** | {has_pos_text} |",
                ]
            report_lines.extend(header + body + [""])

        # ========== 📌 策略选择 ==========
        report_lines.extend(_render_strategy_section(core, labels, report_language))

        # ========== 📊 仓位流水汇总 ==========
        report_lines.extend(_render_position_outcome(
            core.get("position_outcome_summary"), labels,
        ))

        # ========== 行情快照 ==========
        self._append_market_snapshot_to_report(report_lines, result, labels)

        # ========== 数据透视 ==========
        data_persp = dashboard.get('data_perspective', {}) if dashboard else {}
        if data_persp:
            trend_data = data_persp.get('trend_status', {})
            price_data = data_persp.get('price_position', {})
            vol_data = data_persp.get('volume_analysis', {})
            chip_data = data_persp.get('chip_structure', {})

            report_lines.extend([
                f"### 📊 {labels['data_perspective_heading']}",
                "",
            ])
            # 趋势状态
            if trend_data:
                is_bullish = (
                    f"✅ {labels['yes_label']}"
                    if trend_data.get('is_bullish', False)
                    else f"❌ {labels['no_label']}"
                )
                report_lines.extend([
                    f"**{labels['ma_alignment_label']}**: {trend_data.get('ma_alignment', 'N/A')} | "
                    f"{labels['bullish_alignment_label']}: {is_bullish} | "
                    f"{labels['trend_strength_label']}: {trend_data.get('trend_score', 'N/A')}/100",
                    "",
                ])
            # 价格位置
            if price_data:
                raw_bias_status = price_data.get('bias_status', 'N/A')
                bias_status = localize_bias_status(raw_bias_status, report_language)
                bias_emoji = get_bias_status_emoji(raw_bias_status)
                report_lines.extend([
                    f"| {labels['price_metrics_label']} | {labels['current_price_label']} |",
                    "|---------|------|",
                    f"| {labels['current_price_label']} | {price_data.get('current_price', 'N/A')} |",
                    f"| {labels['ma5_label']} | {price_data.get('ma5', 'N/A')} |",
                    f"| {labels['ma10_label']} | {price_data.get('ma10', 'N/A')} |",
                    f"| {labels['ma20_label']} | {price_data.get('ma20', 'N/A')} |",
                    f"| {labels['bias_ma5_label']} | {price_data.get('bias_ma5', 'N/A')}% {bias_emoji}{bias_status} |",
                    f"| {labels['support_level_label']} | {price_data.get('support_level', 'N/A')} |",
                    f"| {labels['resistance_level_label']} | {price_data.get('resistance_level', 'N/A')} |",
                    "",
                ])
            # 量能分析
            if vol_data:
                report_lines.extend([
                    f"**{labels['volume_label']}**: {labels['volume_ratio_label']} {vol_data.get('volume_ratio', 'N/A')} "
                    f"({vol_data.get('volume_status', '')}) | {labels['turnover_rate_label']} {vol_data.get('turnover_rate', 'N/A')}%",
                    f"💡 *{vol_data.get('volume_meaning', '')}*",
                    "",
                ])
            # 筹码结构
            if chip_data:
                raw_chip_health = chip_data.get('chip_health', 'N/A')
                chip_health = localize_chip_health(raw_chip_health, report_language)
                normalized_chip_health = str(raw_chip_health or "").strip().lower()
                if normalized_chip_health in {"健康", "healthy"}:
                    chip_emoji = "✅"
                elif normalized_chip_health in {"一般", "average"}:
                    chip_emoji = "⚠️"
                else:
                    chip_emoji = "🚨"
                report_lines.extend([
                    f"**{labels['chip_label']}**: {chip_data.get('profit_ratio', 'N/A')} | {chip_data.get('avg_cost', 'N/A')} | "
                    f"{chip_data.get('concentration', 'N/A')} {chip_emoji}{chip_health}",
                    "",
                ])

        # ========== 作战计划 ==========
        battle = dashboard.get('battle_plan', {}) if dashboard else {}
        if battle:
            report_lines.extend([
                f"### 🎯 {labels['battle_plan_heading']}",
                "",
            ])
            # When a structured operation plan exists, signal to the reader that the
            # battle plan below is the at-a-glance reference and the detailed playbook
            # lives in the action_plan_items section above.
            if action_plan_items and report_language != "en":
                report_lines.extend([
                    "_关键点位速查（多步骤执行计划见上方「📋 持仓操作计划」）_",
                    "",
                ])
            elif action_plan_items:
                report_lines.extend([
                    "_Key levels at a glance (see the structured action plan above for the executable playbook)._",
                    "",
                ])
            # 狙击点位
            sniper = battle.get('sniper_points', {})
            if sniper:
                report_lines.append(f"**📍 {labels['action_points_heading']}**")
                report_lines.append("")
                if core.get('recommended_strategy') == 'wait_and_see':
                    report_lines.append(labels.get('action_points_wait_notice', ''))
                    report_lines.append("")
                report_lines.extend([
                    f"| {labels['action_points_heading']} | {labels['trigger_price_label']} |",
                    "|---------|------|",
                    f"| 🎯 {labels['ideal_buy_label']} | {self._clean_sniper_value(sniper.get('ideal_buy', 'N/A'))} |",
                    f"| 🔵 {labels['secondary_buy_label']} | {self._clean_sniper_value(sniper.get('secondary_buy', 'N/A'))} |",
                    f"| 🛑 {labels['stop_loss_label']} | {self._clean_sniper_value(sniper.get('stop_loss', 'N/A'))} |",
                    f"| 🎊 {labels['take_profit_label']} | {self._clean_sniper_value(sniper.get('take_profit', 'N/A'))} |",
                    "",
                ])
            # 仓位策略
            position = battle.get('position_strategy', {})
            if position:
                # When the user is already a holder, "建仓策略" is awkward — rename to
                # "调仓策略" so the entry-strategy text reads as position adjustment.
                entry_label = labels['entry_plan_label']
                if (
                    getattr(result, "portfolio_match", None) == "held"
                    and report_language != "en"
                    and entry_label == "建仓策略"
                ):
                    entry_label = "调仓策略"
                report_lines.extend([
                    f"**💰 {labels['suggested_position_label']}**: {position.get('suggested_position', 'N/A')}",
                    f"- {entry_label}: {position.get('entry_plan', 'N/A')}",
                    f"- {labels['risk_control_label']}: {position.get('risk_control', 'N/A')}",
                    "",
                ])
            # 检查清单
            checklist = battle.get('action_checklist', []) if battle else []
            if checklist:
                report_lines.extend([
                    f"**✅ {labels['checklist_heading']}**",
                    "",
                ])
                for item in checklist:
                    report_lines.append(f"- {item}")
                report_lines.append("")

        # ========== 如果没有 dashboard，显示传统格式 ==========
        if not dashboard:
            # 操作理由
            if result.buy_reason:
                report_lines.extend([
                    f"**💡 {reason_label}**: {result.buy_reason}",
                    "",
                ])
            # 风险提示
            if result.risk_warning:
                report_lines.extend([
                    f"**⚠️ {risk_warning_label}**: {result.risk_warning}",
                    "",
                ])
            # 技术面分析
            if result.ma_analysis or result.volume_analysis:
                report_lines.extend([
                    f"### 📊 {technical_heading}",
                    "",
                ])
                if result.ma_analysis:
                    report_lines.append(f"**{ma_label}**: {result.ma_analysis}")
                if result.volume_analysis:
                    report_lines.append(f"**{volume_analysis_label}**: {result.volume_analysis}")
                report_lines.append("")
            # 消息面
            if result.news_summary:
                report_lines.extend([
                    f"### 📰 {news_heading}",
                    f"{result.news_summary}",
                    "",
                ])

        # ========== Sprint 1A: Investment Committee Minutes ==========
        committee_data = dashboard.get("committee") if dashboard else None
        if committee_data:
            try:
                report_lines.extend(
                    _render_committee_minutes(committee_data, labels, report_language)
                )
            except Exception as exc:
                logger.warning("[committee] render failed in history report: %s", exc)

        # ========== Sprint 4: standalone structured Risk Assessment ==========
        # Lives at ``result.dashboard["risk_assessment"]`` and is independent
        # of the committee path.  Renders only when the opt-in flag attached
        # a payload to the dashboard.
        risk_assessment_data = dashboard.get("risk_assessment") if dashboard else None
        if risk_assessment_data:
            try:
                report_lines.extend(
                    _render_structured_risk(risk_assessment_data, report_language)
                )
            except Exception as exc:
                logger.warning("[risk_assessment] render failed in history report: %s", exc)

        # ========== 底部 ==========
        report_lines.extend([
            "---",
            "",
            f"*{labels['generated_at_label']}: {report_time}*",
        ])

        return "\n".join(report_lines)

    @staticmethod
    def _escape_md(text: Optional[str]) -> str:
        """Escape markdown special characters."""
        if not text:
            return ""
        return text.replace('*', r'\*')

    @staticmethod
    def _clean_sniper_value(value: Any) -> str:
        """Clean sniper point value for display."""
        if value is None:
            return "N/A"
        text = str(value).strip()
        if not text or text in ("-", "—", "N/A", "None"):
            return "N/A"
        return text

    def _get_signal_level(self, result: AnalysisResult) -> Tuple[str, str, str]:
        """Get signal level based on sentiment score and decision type."""
        return get_signal_level(
            result.operation_advice,
            result.sentiment_score,
            getattr(result, "report_language", "zh"),
        )

    @staticmethod
    def _safe_format_number(value: Any, fmt: str = ".2f") -> str:
        """
        Safely format a numeric value that may be a string.

        Args:
            value: The value to format (may be int, float, or string like "12.34" or "N/A")
            fmt: Format string (default: ".2f")

        Returns:
            Formatted string or original string if not a valid number
        """
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            return f"{value:{fmt}}"
        if isinstance(value, str):
            value = value.strip()
            if not value or value in ("N/A", "-", "—", "None"):
                return "N/A"
            try:
                return f"{float(value):{fmt}}"
            except (ValueError, TypeError):
                return value
        return str(value)

    @staticmethod
    def _append_market_snapshot_to_report(
        lines: List[str],
        result: AnalysisResult,
        labels: Dict[str, str],
    ) -> None:
        """Append market snapshot data to report lines."""
        snapshot = getattr(result, 'market_snapshot', None)
        if not snapshot:
            return

        lines.extend([
            f"### 📈 {labels['market_snapshot_heading']}",
            "",
            f"| {labels['price_metrics_label']} | {labels['current_price_label']} |",
            "|------|------|",
        ])

        # Price info
        current_price = snapshot.get('price') or snapshot.get('current_price') or result.current_price
        change_pct = snapshot.get('change_pct') or snapshot.get('pct_chg') or result.change_pct
        if current_price is not None:
            current_str = HistoryService._safe_format_number(current_price, ".2f")
            if change_pct is not None:
                if isinstance(change_pct, str) and change_pct.strip().endswith("%"):
                    change_str = change_pct.strip()
                else:
                    change_str = f"{HistoryService._safe_format_number(change_pct, '+.2f')}%"
            else:
                change_str = "--"
            lines.append(f"| {labels['current_price_label']} | **{current_str}** ({change_str}) |")

        # Other metrics
        metrics = [
            (labels['open_label'], "open", ".2f"),
            (labels['high_label'], "high", ".2f"),
            (labels['low_label'], "low", ".2f"),
            (labels['volume_label'], "volume", ",.0f"),
            (labels['amount_label'], "amount", ",.0f"),
        ]
        for label, key, fmt in metrics:
            value = snapshot.get(key)
            if value is not None:
                formatted = HistoryService._safe_format_number(value, fmt)
                lines.append(f"| {label} | {formatted} |")

        lines.extend(["", "---", ""])
