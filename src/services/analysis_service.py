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
from typing import Optional, Dict, Any, Callable

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
    ) -> Optional[Dict[str, Any]]:
        """
        执行股票分析
        
        Args:
            stock_code: 股票代码
            report_type: 报告类型 (simple/detailed)
            force_refresh: 是否强制刷新
            query_id: 查询 ID（可选）
            send_notification: 是否发送通知（API 触发默认发送）
            
        Returns:
            分析结果字典，包含:
            - stock_code: 股票代码
            - stock_name: 股票名称
            - report: 分析报告
        """
        try:
            self.last_error = None
            # 导入分析相关模块
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType

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

            # 创建分析流水线
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                query_source="api",
                progress_callback=progress_callback,
                portfolio_context_block=portfolio_context_block,
                portfolio_match=portfolio_match,
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
            return self._build_analysis_response(result, query_id, report_type=rt.value)
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"分析股票 {stock_code} 失败: {e}", exc_info=True)
            return None
    
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
