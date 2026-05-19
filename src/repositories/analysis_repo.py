# -*- coding: utf-8 -*-
"""
===================================
分析历史数据访问层
===================================

职责：
1. 封装分析历史数据的数据库操作
2. 提供 CRUD 接口
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.storage import DatabaseManager, AnalysisHistory

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """
    分析历史数据访问层
    
    封装 AnalysisHistory 表的数据库操作
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        初始化数据访问层
        
        Args:
            db_manager: 数据库管理器（可选，默认使用单例）
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_by_query_id(self, query_id: str) -> Optional[AnalysisHistory]:
        """
        根据 query_id 获取分析记录
        
        Args:
            query_id: 查询 ID
            
        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        try:
            records = self.db.get_analysis_history(query_id=query_id, limit=1)
            return records[0] if records else None
        except Exception as e:
            logger.error(f"查询分析记录失败: {e}")
            return None
    
    def get_list(
        self,
        code: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[AnalysisHistory]:
        """
        获取分析记录列表
        
        Args:
            code: 股票代码筛选
            days: 时间范围（天）
            limit: 返回数量限制
            
        Returns:
            AnalysisHistory 对象列表
        """
        try:
            return self.db.get_analysis_history(
                code=code,
                days=days,
                limit=limit
            )
        except Exception as e:
            logger.error(f"获取分析列表失败: {e}")
            return []
    
    def save(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存分析结果

        Args:
            result: 分析结果对象
            query_id: 查询 ID
            report_type: 报告类型
            news_content: 新闻内容
            context_snapshot: 上下文快照

        Returns:
            保存的记录数
        """
        try:
            return self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type=report_type,
                news_content=news_content,
                context_snapshot=context_snapshot
            )
        except Exception as e:
            logger.error(f"保存分析结果失败: {e}")
            return 0

    def update_committee_minutes(
        self,
        query_id: str,
        committee: Dict[str, Any],
    ) -> bool:
        """Patch ``raw_result.dashboard.committee`` on an existing history row.

        Sprint 1A locked decision #4 — committee minutes must persist
        alongside the report so the history page and Sprint 2 reflection
        can read them back.  We patch the most-recent row matching
        ``query_id`` (the pipeline writes one INSERT per analysis run).

        Returns True on a successful patch, False otherwise (silent failure
        keeps the live report intact — committee persistence is best-effort
        per spec §11 graceful-degradation rule).
        """
        import json
        logger.info("[update_committee_minutes] start query_id=%s", query_id)
        try:
            records = self.db.get_analysis_history(query_id=query_id, limit=1)
        except Exception as exc:
            logger.warning("[update_committee_minutes] lookup failed: %s", exc)
            return False
        if not records:
            logger.warning(
                "[update_committee_minutes] no record found for query_id=%s",
                query_id,
            )
            return False
        record = records[0]
        logger.info(
            "[update_committee_minutes] found record id=%s code=%s",
            getattr(record, "id", "?"), getattr(record, "code", "?"),
        )
        raw = getattr(record, "raw_result", None)
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except Exception as exc:
                logger.warning(
                    "[update_committee_minutes] raw_result JSON parse failed: %s", exc,
                )
                return False
        elif isinstance(raw, dict):
            payload = dict(raw)
        else:
            logger.warning(
                "[update_committee_minutes] raw_result has unexpected type=%s",
                type(raw).__name__,
            )
            payload = {}
        dashboard = payload.get("dashboard")
        if not isinstance(dashboard, dict):
            dashboard = {}
        dashboard["committee"] = committee
        payload["dashboard"] = dashboard
        try:
            with self.db.get_session() as session:
                row = (
                    session.query(AnalysisHistory)
                    .filter(AnalysisHistory.id == record.id)
                    .one_or_none()
                )
                if row is None:
                    logger.warning(
                        "[update_committee_minutes] session.query returned None for id=%s",
                        record.id,
                    )
                    return False
                row.raw_result = json.dumps(payload, ensure_ascii=False, default=str)
                session.flush()
                logger.info(
                    "[update_committee_minutes] DONE id=%s payload_size=%d bytes",
                    record.id, len(row.raw_result),
                )
                return True
        except Exception as exc:
            logger.warning("[update_committee_minutes] persist failed: %s", exc, exc_info=True)
            return False
    
    def count_by_code(self, code: str, days: int = 30) -> int:
        """
        统计指定股票的分析记录数
        
        Args:
            code: 股票代码
            days: 时间范围（天）
            
        Returns:
            记录数量
        """
        try:
            records = self.db.get_analysis_history(code=code, days=days, limit=1000)
            return len(records)
        except Exception as e:
            logger.error(f"统计分析记录失败: {e}")
            return 0
