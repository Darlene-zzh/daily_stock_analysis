# -*- coding: utf-8 -*-
"""
===================================
分析服务层
===================================

职责：
1. 封装股票分析逻辑
2. 调用 analyzer 和 pipeline 执行分析
3. 保存分析结果到数据库
"""

import json
import logging
import uuid
from typing import Optional, Dict, Any, Callable, List

from src.repositories.analysis_repo import AnalysisRepository
from src.report_language import (
    get_sentiment_label,
    get_localized_stock_name,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    分析服务
    
    封装股票分析相关的业务逻辑
    """
    
    def __init__(self):
        """初始化分析服务"""
        self.repo = AnalysisRepository()
        self.last_error: Optional[str] = None
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        send_notification: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        portfolio_context_block: Optional[str] = None,
        portfolio_match: Optional[str] = None,
        portfolio_account_id: Optional[int] = None,
        enable_investment_committee: bool = False,
        committee_debate_rounds: int = 2,
        enable_decision_journal_reflection: bool = False,
        enable_quant_signal: bool = False,
        quant_forecast_horizon: Optional[int] = None,
        enable_structured_risk: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        执行股票分析

        Args:
            stock_code: 股票代码
            report_type: 报告类型 (simple/detailed)
            force_refresh: 是否强制刷新
            query_id: 查询 ID（可选）
            send_notification: 是否发送通知（API 触发默认发送）
            enable_investment_committee: 是否启用投委会多智能体补全流程
                （Sprint 1A opt-in；默认关闭，对默认链路零影响）
            committee_debate_rounds: 投委会 Bull/Bear 辩论轮数，1~3，默认 2
            enable_decision_journal_reflection: 是否将历史决策日志作为
                反思上下文注入到本次 prompt（Sprint 2 opt-in；默认关闭，
                journal 写入始终发生但只有显式开启才会读出来）。
            enable_quant_signal: Sprint 3 opt-in — 是否在 prompt 中拼入
                qlib Alpha158 + LightGBM 的辅助量化信号；默认关闭。当 qlib
                未安装 / 无模型权重 / 个股不在锁定池中（CSI 300 / S&P 500）
                时静默 no-op，绝不抛错。HK 标的同样静默 no-op。
            quant_forecast_horizon: 预测期（交易日数）；None 时使用默认值
                ``QUANT_FORECAST_HORIZON`` 环境变量（默认 10）。

        Returns:
            分析结果字典，包含:
            - stock_code: 股票代码
            - stock_name: 股票名称
            - report: 分析报告（opt-in 时含 ``report["committee"]`` 字段）
        """
        try:
            self.last_error = None
            # 导入分析相关模块
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType

            # Sprint 1A/2/3/4 entry diagnostic: capture the opt-in flags
            # received from the API so we can confirm toggle clicks
            # actually reach the backend.
            logger.info(
                "[analyze_stock] entry %s | committee=%s rounds=%s "
                "journal=%s quant=%s structured_risk=%s portfolio_acct=%s",
                stock_code,
                enable_investment_committee, committee_debate_rounds,
                enable_decision_journal_reflection, enable_quant_signal,
                enable_structured_risk, portfolio_account_id,
            )

            # P0.3: 同日同股 24h 报告缓存。默认开启（ANALYSIS_CACHE_HOURS=24），
            # 同一只股 24h 内重复点「分析」不再烧 LLM 配额，直接返回缓存报告。
            # force_refresh=True 或 ANALYSIS_CACHE_HOURS=0 时绕过。
            if not force_refresh:
                cached = self._lookup_recent_cache_response(stock_code, report_type)
                if cached is not None:
                    return cached

            # 如果通过 task_queue 异步路径传来 portfolio_account_id 而没有 block，自动构建
            if portfolio_account_id is not None and portfolio_context_block is None:
                try:
                    from src.report_language import normalize_report_language
                    from src.services.portfolio_context_service import (
                        PortfolioContextService,
                        render_portfolio_context_block,
                    )
                    _ctx = PortfolioContextService().get_context(
                        account_id=portfolio_account_id, symbol=stock_code
                    )
                    if _ctx is not None:
                        _lang = normalize_report_language(
                            getattr(get_config(), "report_language", "zh")
                        )
                        portfolio_context_block = render_portfolio_context_block(_ctx, language=_lang)
                        portfolio_match = "held" if _ctx.is_held else "not_held"
                except Exception as _exc:
                    logger.warning("portfolio_account_id 上下文构建失败: %s", _exc)

            # 生成 query_id
            if query_id is None:
                query_id = uuid.uuid4().hex

            # 获取配置
            config = get_config()

            # Sprint 2: build the reflection block BEFORE the pipeline runs
            # so the analyzer can splice it into the prompt.  Default-off —
            # caller must opt-in.  Failure here MUST NOT kill the request.
            reflection_context_block: Optional[str] = None
            if enable_decision_journal_reflection:
                try:
                    from src.services.decision_journal_service import (
                        DecisionJournalService,
                        default_token_budget,
                        infer_market_from_code,
                    )
                    _journal = DecisionJournalService()
                    reflection_context_block = _journal.build_reflection_block(
                        stock_code=stock_code,
                        market=infer_market_from_code(stock_code),
                        token_budget=default_token_budget(),
                    )
                except Exception as _exc:
                    logger.warning(
                        "[analyze_stock] reflection block build failed for %s: %s",
                        stock_code, _exc,
                    )

            # Sprint 3: build the quant context block (Alpha158 + LightGBM
            # forecast).  Mirrors the reflection hook above — built BEFORE
            # the pipeline starts so analyzer.analyze() can splice it.
            # All failure modes (no qlib / no model / outside universe /
            # low IC) return None silently — never kills the request.
            quant_context_block: Optional[str] = None
            if enable_quant_signal:
                try:
                    from src.services.quant_signal_service import (
                        QuantSignalService,
                        infer_market_from_code as infer_quant_market,
                    )
                    from src.report_language import normalize_report_language
                    _quant = QuantSignalService()
                    _quant_market = infer_quant_market(stock_code)
                    _quant_lang = normalize_report_language(
                        getattr(get_config(), "report_language", "zh")
                    )
                    quant_context_block = _quant.build_quant_context_block(
                        stock_code=stock_code,
                        market=_quant_market,
                        horizon=quant_forecast_horizon,
                        language=_quant_lang,
                    )
                except Exception as _exc:
                    logger.warning(
                        "[analyze_stock] quant block build failed for %s: %s",
                        stock_code, _exc,
                    )

            # 创建分析流水线
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                query_source="api",
                progress_callback=progress_callback,
                portfolio_context_block=portfolio_context_block,
                portfolio_match=portfolio_match,
                reflection_context_block=reflection_context_block,
                quant_context_block=quant_context_block,
            )
            
            # 确定报告类型 (API: simple/detailed/full/brief -> ReportType)
            rt = ReportType.from_str(report_type)
            
            # 执行分析
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt,
            )
            
            if result is None:
                logger.warning(f"分析股票 {stock_code} 返回空结果")
                self.last_error = self.last_error or f"分析股票 {stock_code} 返回空结果"
                return None

            if not getattr(result, "success", True):
                self.last_error = getattr(result, "error_message", None) or f"分析股票 {stock_code} 失败"
                logger.warning(f"分析股票 {stock_code} 未成功完成: {self.last_error}")
                return None

            # 构建响应
            response = self._build_analysis_response(result, query_id, report_type=rt.value)

            # Sprint 2: write a journal entry for this analysis.  Runs for
            # BOTH the standard pipeline and the agent-mode bypass path
            # because both converge here on the response object.  This is
            # always-on (the read side is opt-in) so the user accumulates
            # data immediately and can switch reflection on later without
            # a cold start.  Failure MUST NEVER kill the response.
            self._write_journal_entry_safe(
                stock_code=stock_code,
                result=result,
                response=response,
                query_id=query_id,
            )

            # Sprint 1A: Investment Committee hook.
            # We attach committee minutes to ``response["report"]["committee"]``
            # AFTER the default analysis has succeeded.  This runs identically
            # for both the standard pipeline path and the ``_analyze_with_agent``
            # bypass path because both converge here.  Default analysis is
            # untouched when ``enable_investment_committee=False``.
            if enable_investment_committee and response is not None:
                try:
                    # Backward-compat: existing tests may monkey-patch
                    # ``_invoke_committee`` with the Sprint 1A signature
                    # that pre-dates ``query_id``.  Detect & degrade.
                    _committee_kwargs = dict(
                        stock_code=stock_code,
                        result=result,
                        response=response,
                        debate_rounds=committee_debate_rounds,
                    )
                    logger.info(
                        "[committee-hook] %s: invoking committee orchestrator "
                        "(rounds=%s, query_id=%s)",
                        stock_code, committee_debate_rounds, query_id,
                    )
                    try:
                        committee_payload = self._invoke_committee(
                            **_committee_kwargs, query_id=query_id,
                        )
                    except TypeError:
                        # Test-only fallback path for stubs that pre-date
                        # the Sprint 4 ``query_id`` kwarg.
                        committee_payload = self._invoke_committee(**_committee_kwargs)
                    logger.info(
                        "[committee-hook] %s: _invoke_committee returned "
                        "type=%s status=%s",
                        stock_code,
                        type(committee_payload).__name__,
                        (committee_payload or {}).get("status")
                            if isinstance(committee_payload, dict) else None,
                    )
                    if committee_payload is not None:
                        response.setdefault("report", {})["committee"] = committee_payload
                        # Also expose on the result.dashboard so the standard
                        # renderers (notification + history) can pick it up
                        # via the same path other dashboard sub-sections use.
                        dash = getattr(result, "dashboard", None)
                        if isinstance(dash, dict):
                            dash["committee"] = committee_payload
                        # Locked decision #4: persist minutes alongside the
                        # full report so the history page + Sprint 2
                        # reflection can read them back.  Best-effort —
                        # persistence failure does NOT kill the response.
                        try:
                            self.repo.update_committee_minutes(query_id, committee_payload)
                        except Exception as p_exc:
                            logger.warning(
                                "[analyze_stock] committee persist failed: %s", p_exc,
                            )
                except Exception as exc:
                    # Committee failure must NEVER kill the default report.
                    logger.warning(
                        "[analyze_stock] investment committee hook failed for %s: %s",
                        stock_code, exc, exc_info=True,
                    )

            # Sprint 4: structured Risk Manager hook.  Wraps the existing
            # ``RiskAgent`` to emit a standalone ``risk_assessment`` payload
            # (severity / suggested position % / tail-risk / VaR) on top of
            # the regular report.  Independent of the committee path —
            # works even when ``enable_investment_committee=False``.
            # Default-off and best-effort: any failure leaves the response
            # untouched.
            if enable_structured_risk and response is not None:
                try:
                    risk_payload = self._invoke_structured_risk(
                        stock_code=stock_code,
                        result=result,
                        response=response,
                    )
                    if risk_payload is not None:
                        response["risk_assessment"] = risk_payload
                        # Also expose on result.dashboard so the existing
                        # notification + history renderers can surface it
                        # via the same path the committee callout uses.
                        dash = getattr(result, "dashboard", None)
                        if isinstance(dash, dict):
                            dash["risk_assessment"] = risk_payload
                except Exception as exc:
                    logger.warning(
                        "[analyze_stock] structured risk hook failed for %s: %s",
                        stock_code, exc, exc_info=True,
                    )

            return response
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"分析股票 {stock_code} 失败: {e}", exc_info=True)
            return None
    
    def _write_journal_entry_safe(
        self,
        *,
        stock_code: str,
        result: Any,
        response: Dict[str, Any],
        query_id: Optional[str],
    ) -> None:
        """Append a Sprint 2 decision-journal entry.

        Wraps every step in try/except — a misconfigured journal directory,
        a disk-full event, or a fetch failure for ``price_at_decision`` MUST
        NOT propagate.  Log + swallow.
        """
        try:
            from src.services.decision_journal_service import (
                DecisionJournalService,
                infer_market_from_code,
            )

            # Extract action-plan fields from the response in a forgiving way.
            report = (response or {}).get("report") or {}
            summary = report.get("summary") or {}
            details = report.get("details") or {}

            verdict = (
                summary.get("operation_advice")
                or getattr(result, "operation_advice", None)
                or None
            )
            score = summary.get("sentiment_score")
            if score is None:
                score = getattr(result, "sentiment_score", None)
            one_sentence = (
                summary.get("analysis_summary")
                or getattr(result, "analysis_summary", None)
                or ""
            )

            # Committee verdict — only present when committee opt-in fired
            committee = report.get("committee") or {}
            pm = (committee.get("pm") or {}) if isinstance(committee, dict) else {}
            committee_pm_verdict = pm.get("verdict") if isinstance(pm, dict) else None

            # Risks → use the analyser's risk_warning list if available
            risk_warning = details.get("risk_warning") or getattr(result, "risk_warning", "")
            key_risks: List[str] = self._coerce_to_list(risk_warning)

            # Catalysts → fallback to key_points / buy_reason (the analyser
            # populates these for the "why I think this" narrative).
            catalysts_seed = getattr(result, "key_points", "") or getattr(
                result, "buy_reason", ""
            )
            key_catalysts: List[str] = self._coerce_to_list(catalysts_seed)

            price_at_decision = getattr(result, "current_price", None)

            journal = DecisionJournalService()
            journal.write_entry(
                stock_code=stock_code,
                market=infer_market_from_code(stock_code),
                verdict=verdict,
                score=int(score) if isinstance(score, (int, float)) else None,
                one_sentence=one_sentence,
                price_at_decision=price_at_decision,
                report_language=getattr(result, "report_language", None),
                committee_pm_verdict=committee_pm_verdict,
                key_catalysts=key_catalysts,
                key_risks=key_risks,
                analysis_query_id=query_id,
            )
        except Exception as exc:
            logger.warning(
                "[analyze_stock] decision-journal write failed for %s: %s",
                stock_code,
                exc,
            )

    @staticmethod
    def _coerce_to_list(value: Any) -> list:
        """Best-effort string/list normalisation for journal bullets."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if v is not None and str(v).strip()]
        if isinstance(value, str):
            # Split on Chinese bullet ・/ newline / semicolon — keeps short
            # entries while breaking up "risk1; risk2; risk3" style strings.
            import re
            parts = re.split(r"[\n;；]+", value)
            return [p.strip(" -·•\t") for p in parts if p and p.strip(" -·•\t")]
        return [str(value)]

    def _invoke_committee(
        self,
        *,
        stock_code: str,
        result: Any,
        response: Dict[str, Any],
        debate_rounds: int,
        **_kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Run the Investment Committee pipeline and return the minutes dict.

        Returns ``None`` if the committee was skipped (e.g. LLM not configured).
        Errors from the committee are NEVER allowed to propagate — callers
        catch broad exceptions; this helper logs and returns None on hard
        failure paths.
        """
        # Local import keeps the cold-start path cheap when the feature is
        # not opted in.
        from src.agent.budget import (
            LLMCallBudget,
            compute_effective_cap,
            resolve_timeout_s,
        )
        from src.agent.llm_adapter import LLMToolAdapter
        from src.agent.orchestrator_committee import InvestmentCommitteeOrchestrator
        from src.agent.protocols import AgentContext
        from src.config import get_config
        from data_provider.akshare_fetcher import is_hk_stock_code
        from data_provider.base import normalize_stock_code
        from data_provider.us_index_mapping import is_us_stock_code

        cap = compute_effective_cap(debate_rounds)
        budget = LLMCallBudget(cap=cap)

        config = get_config()
        try:
            adapter = LLMToolAdapter(config=config)
        except Exception as exc:
            logger.warning("[committee] LLMToolAdapter init failed for %s: %s", stock_code, exc)
            return None
        if not getattr(adapter, "_litellm_available", False):
            logger.info("[committee] LLM unavailable — skipping committee for %s", stock_code)
            return None
        logger.info("[committee] %s: adapter OK, cap=%s, building orchestrator", stock_code, cap)

        def _llm_call(system_prompt: str, user_message: str) -> str:
            try:
                resp = adapter.call_text(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    timeout=resolve_timeout_s(),
                )
            except Exception as exc:
                logger.warning("[committee] LLM call_text failed: %s", exc)
                # Return a sentinel string so the orchestrator's strict parse
                # treats it as a schema failure rather than a Python exception.
                return f"<<llm_call_failed: {exc}>>"
            content = resp.content if hasattr(resp, "content") else None
            return content or "<<empty_llm_response>>"

        normalised = normalize_stock_code(stock_code)
        if is_hk_stock_code(normalised):
            market = "HK"
        elif is_us_stock_code(normalised):
            market = "US"
        else:
            market = "A"
        stock_name = response.get("stock_name") or getattr(result, "name", None) or ""
        ctx = AgentContext(
            stock_code=stock_code,
            stock_name=stock_name,
            meta={"market": market},
        )

        # The orchestrator sees the structured response report — keeps it
        # focused on what the LLM needs and avoids pulling raw fetcher
        # internals into the prompt.
        report_for_committee = response.get("report") or {}

        orchestrator = InvestmentCommitteeOrchestrator(
            ctx,
            report_json=report_for_committee,
            budget=budget,
            llm_callable=_llm_call,
            debate_rounds=debate_rounds,
            query_id=_kwargs.get("query_id"),
        )
        try:
            logger.info("[committee] %s: orchestrator.run() start", stock_code)
            run_result = orchestrator.run()
            logger.info(
                "[committee] %s: orchestrator.run() done — status=%s "
                "budget_used=%s missing=%s masters=%d debate=%d",
                stock_code,
                getattr(run_result.minutes, "status", "<no-status>"),
                getattr(run_result.minutes, "budget_used", "?"),
                getattr(run_result.minutes, "missing_agents", []),
                len(getattr(run_result.minutes, "masters", []) or []),
                len(getattr(run_result.minutes, "debate", []) or []),
            )
        except Exception as exc:
            logger.warning(
                "[committee] %s: orchestrator.run() raised %s: %s",
                stock_code, type(exc).__name__, exc, exc_info=True,
            )
            return None
        return run_result.minutes.model_dump()

    def _invoke_structured_risk(
        self,
        *,
        stock_code: str,
        result: Any,
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Compose a standalone ``risk_assessment`` payload (Sprint 4).

        This is intentionally **NOT** a full LLM run — we reuse the
        already-extracted risk signals (LLM-emitted risk flags + price
        history) the analyser collected during the main analysis, then
        feed them into :meth:`RiskAgent.build_structured_assessment`.

        Returns ``None`` when no signal is available so the renderer can
        skip the section cleanly. Callers ALREADY wrap us in try/except,
        so we propagate parser failures intentionally to surface them in
        logs without crashing the response.
        """
        from src.agent.agents.risk_agent import RiskAgent

        # 1) Try the analyser-emitted risk_warning / risk flags first.
        raw_llm: Dict[str, Any] = {}
        report = (response or {}).get("report") or {}
        details = report.get("details") or {}
        risk_warning = (
            details.get("risk_warning")
            or getattr(result, "risk_warning", None)
        )
        flags: List[Dict[str, Any]] = []
        if risk_warning:
            # Split risk_warning into individual flag bullets so the
            # severity heuristic can count "high" entries.
            parts: List[str] = []
            if isinstance(risk_warning, list):
                parts = [str(p).strip() for p in risk_warning if p]
            elif isinstance(risk_warning, str):
                import re
                parts = [
                    p.strip(" -·•\t")
                    for p in re.split(r"[\n;；]+", risk_warning)
                    if p.strip(" -·•\t")
                ]
            for p in parts[:10]:
                # Detect severity heuristically from keyword cues.
                lowered = p.lower()
                severity = "low"
                if any(k in p for k in ("立案", "调查", "退市", "欺诈", "造假")) or any(
                    k in lowered for k in ("delisting", "fraud", "investigation", "lawsuit")
                ):
                    severity = "high"
                elif any(k in p for k in ("减持", "解禁", "业绩预亏", "业绩变脸")) or any(
                    k in lowered for k in ("insider sell", "lock-up", "earnings miss")
                ):
                    severity = "medium"
                flags.append({"category": "analyser", "severity": severity, "description": p})
        if flags:
            raw_llm["flags"] = flags
            # Map highest flag severity into the LLM-style risk_level.
            highest = max((f["severity"] for f in flags), key=lambda s: ("high", "medium", "low").index(s))
            raw_llm["risk_level"] = {"high": "high", "medium": "medium", "low": "low"}[highest]
            raw_llm["risk_score"] = {"high": 75, "medium": 50, "low": 25}[highest]

        # 2) Recent closes — pulled from result.recent_closes when the analyser
        # exposes it; otherwise fall back to None so VaR/vol stay null.
        recent_closes: Optional[List[float]] = None
        for candidate_attr in ("recent_closes", "price_history", "closes"):
            candidate = getattr(result, candidate_attr, None)
            if isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
                try:
                    recent_closes = [float(p) for p in candidate if p is not None]
                    break
                except (TypeError, ValueError):
                    continue

        assessment = RiskAgent.build_structured_assessment(
            raw_llm=raw_llm or None,
            recent_closes=recent_closes,
        )
        # Skip when the assessment has nothing meaningful to say.
        if (
            assessment.severity is None
            and not assessment.red_flags
            and assessment.suggested_position_pct is None
            and assessment.tail_risk_score is None
            and assessment.var_estimate_5pct is None
        ):
            return None
        return assessment.model_dump()

    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str,
        report_type: str = "detailed",
    ) -> Dict[str, Any]:
        """
        构建分析响应
        
        Args:
            result: AnalysisResult 对象
            query_id: 查询 ID
            report_type: 归一化后的报告类型
            
        Returns:
            格式化的响应字典
        """
        # 获取狙击点位
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}
        
        # 计算情绪标签
        report_language = normalize_report_language(getattr(result, "report_language", "zh"))
        sentiment_label = get_sentiment_label(result.sentiment_score, report_language)
        stock_name = get_localized_stock_name(getattr(result, "name", None), result.code, report_language)
        
        # 构建报告结构
        report = {
            "meta": {
                "query_id": query_id,
                "stock_code": result.code,
                "stock_name": stock_name,
                "report_type": report_type,
                "report_language": report_language,
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": localize_operation_advice(result.operation_advice, report_language),
                "trend_prediction": localize_trend_prediction(result.trend_prediction, report_language),
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "details": {
                "news_summary": result.news_summary,
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            }
        }

        # Expose dashboard for frontend structured rendering (action_plan_items, etc.)
        dashboard_raw = getattr(result, "dashboard", None) or {}
        report["dashboard"] = dashboard_raw

        return {
            "stock_code": result.code,
            "stock_name": stock_name,
            "report": report,
        }

    def _lookup_recent_cache_response(
        self, stock_code: str, report_type: str
    ) -> Optional[Dict[str, Any]]:
        """Return a cached `_build_analysis_response` payload for the same stock
        analyzed within the last ``ANALYSIS_CACHE_HOURS`` window.

        Returns None when caching is disabled, no recent record exists, or any
        step fails — caller falls through to a fresh pipeline run in that case.
        """
        import os
        from datetime import datetime

        try:
            cache_hours_raw = os.getenv("ANALYSIS_CACHE_HOURS", "24").strip()
            cache_hours = float(cache_hours_raw) if cache_hours_raw else 0.0
        except ValueError:
            cache_hours = 0.0
        if cache_hours <= 0:
            return None

        try:
            recent_records = self.repo.get_list(code=stock_code, days=1, limit=1)
        except Exception as exc:
            logger.debug("[analyze_stock] cache lookup repo error: %s", exc)
            return None
        if not recent_records:
            return None

        rec = recent_records[0]
        raw_payload = getattr(rec, "raw_result", None)
        if not raw_payload:
            return None
        created_at = getattr(rec, "created_at", None)
        if created_at is None:
            return None
        age_seconds = (datetime.now() - created_at).total_seconds()
        if age_seconds < 0 or age_seconds > cache_hours * 3600.0:
            return None

        try:
            from src.analyzer import AnalysisResult
            from dataclasses import fields as dc_fields
            payload: Dict[str, Any]
            if isinstance(raw_payload, str):
                payload = json.loads(raw_payload)
            elif isinstance(raw_payload, dict):
                payload = raw_payload
            else:
                return None
            if not payload.get("success", True):
                return None  # do not cache failed analyses
            valid_keys = {f.name for f in dc_fields(AnalysisResult)}
            ctor_kwargs = {k: v for k, v in payload.items() if k in valid_keys}
            # `code` and `name` are required positional fields of the dataclass
            if "code" not in ctor_kwargs:
                ctor_kwargs["code"] = stock_code
            if "name" not in ctor_kwargs:
                ctor_kwargs["name"] = getattr(rec, "stock_name", None) or stock_code
            # required-ish fields must be present even if upstream omitted
            for required in ("sentiment_score", "trend_prediction", "operation_advice"):
                ctor_kwargs.setdefault(required, payload.get(required, 0 if required == "sentiment_score" else ""))
            result = AnalysisResult(**ctor_kwargs)
        except Exception as exc:
            logger.info(
                "[analyze_stock] cache reconstruction failed for %s (%s); will run live",
                stock_code, exc,
            )
            return None

        response = self._build_analysis_response(
            result, getattr(rec, "query_id", None) or stock_code, report_type=report_type
        )
        meta = response.setdefault("report", {}).setdefault("meta", {})
        meta["cached"] = True
        meta["cached_at"] = created_at.isoformat()
        meta["cache_age_seconds"] = int(age_seconds)
        logger.info(
            "[analyze_stock] cache HIT for %s (age=%ds, limit=%.1fh) — skipping LLM call",
            stock_code, int(age_seconds), cache_hours,
        )
        return response
