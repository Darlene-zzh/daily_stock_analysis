import React from 'react';
import type { AnalysisResult, AnalysisReport } from '../../types/analysis';
import { CommitteeMinutesPanel } from '../committee/CommitteeMinutesPanel';
import { DecisionTrackingTab } from '../decisionTracking/DecisionTrackingTab';
import { QuantContextPanel } from '../quant/QuantContextPanel';
import { StructuredRiskCallout } from '../risk/StructuredRiskCallout';
import { ReportOverview } from './ReportOverview';
import { ActionPlanTable } from './ActionPlanTable';
import { StrategySelector } from './StrategySelector';
import { StrategyThesis } from './StrategyThesis';
import { SentimentPanel } from './SentimentPanel';
import { PositionOutcomeSummary } from './PositionOutcomeSummary';
import { ReportStrategy } from './ReportStrategy';
import { ReportNews } from './ReportNews';
import { ReportDetails } from './ReportDetails';
import { InlineAlert, Button } from '../common';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  isHistory?: boolean;
  /**
   * Called when the user wants to bypass the 24h same-stock cache and
   * re-run a fresh analysis. The banner that surfaces this is only shown
   * when the backend served a cached result (`report.meta.cached === true`).
   */
  onForceRefresh?: (stockCode: string) => void;
}

/** Render "X 小时 Y 分钟前" given a number of seconds. */
function formatCacheAge(seconds?: number): string {
  if (!seconds || seconds <= 0) return '刚刚';
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return mins > 0 ? `${hours} 小时 ${mins} 分钟前` : `${hours} 小时前`;
}

/**
 * 完整报告展示组件
 * 整合概览、策略、资讯、详情四个区域
 */
export const ReportSummary: React.FC<ReportSummaryProps> = ({
  data,
  isHistory = false,
  onForceRefresh,
}) => {
  // 兼容 AnalysisResult 和 AnalysisReport 两种数据格式
  const report: AnalysisReport = 'report' in data ? data.report : data;
  // 使用 report id，因为 queryId 在批量分析时可能重复，且历史报告详情接口需要 recordId 来获取关联资讯和详情数据
  const recordId = report.meta.id;

  const { meta, summary, strategy, details, committee, riskAssessment } = report;
  const reportLanguage = normalizeReportLanguage(meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const modelUsed = (meta.modelUsed || '').trim();
  const shouldShowModel = Boolean(
    modelUsed && !['unknown', 'error', 'none', 'null', 'n/a'].includes(modelUsed.toLowerCase()),
  );
  // 24h same-stock cache hint — banner only shows when backend served a
  // cached payload (P0.3 ANALYSIS_CACHE_HOURS). Without this banner the user
  // re-submits the same ticker, sees the prior report come back unchanged,
  // and assumes the page is broken.
  const isCached = meta.cached === true;
  const cacheAgeLabel = isCached ? formatCacheAge(meta.cacheAgeSeconds) : '';

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      {isCached && (
        <InlineAlert
          variant="info"
          title={`今日已分析过 ${meta.stockCode}`}
          message={
            <span>
              下面是 <b>{cacheAgeLabel}</b> 的分析结果，为节省额度直接展示缓存。
              数据/价格可能已过期，如需重新分析请点击右侧按钮。
            </span>
          }
          action={
            onForceRefresh ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onForceRefresh(meta.stockCode)}
              >
                强制刷新
              </Button>
            ) : undefined
          }
        />
      )}
      {/* 概览区（首屏） */}
      <ReportOverview
        meta={meta}
        summary={summary}
        details={details}
        isHistory={isHistory}
      />

      {/* 结构化持仓操作计划（当 action_plan_items 存在时显示） */}
      {report.dashboard?.coreConclusion?.actionPlanItems &&
        report.dashboard.coreConclusion.actionPlanItems.length > 0 && (
          <div className="rounded-xl border border-subtle bg-card p-4">
            <ActionPlanTable items={report.dashboard.coreConclusion.actionPlanItems} />
          </div>
        )}

      {/* 策略选择 — 4 个候选 + AI 推荐 + 论述 */}
      {report.dashboard?.coreConclusion?.strategyChoices &&
        report.dashboard.coreConclusion.strategyChoices.length > 0 && (
          <div className="rounded-xl border border-subtle bg-card p-4 space-y-3">
            <StrategySelector
              choices={report.dashboard.coreConclusion.strategyChoices}
              recommendedId={report.dashboard.coreConclusion.recommendedStrategy}
            />
            {report.dashboard.coreConclusion.strategyThesis && (
              <StrategyThesis
                thesis={report.dashboard.coreConclusion.strategyThesis}
                recommendedLabel={undefined}
              />
            )}
          </div>
        )}

      {/* 仓位流水汇总 */}
      {report.dashboard?.coreConclusion?.positionOutcomeSummary && (
        <PositionOutcomeSummary
          summary={report.dashboard.coreConclusion.positionOutcomeSummary}
        />
      )}

      {/* 市场情绪面板 */}
      {report.dashboard?.intelligence &&
        (report.dashboard.intelligence as { sentimentDimensions?: import('../../types/analysis').SentimentDimensions })
          .sentimentDimensions && (
          <SentimentPanel
            dimensions={(report.dashboard.intelligence as {
              sentimentDimensions: import('../../types/analysis').SentimentDimensions;
            }).sentimentDimensions}
          />
        )}

      {/* 策略点位区 */}
      <ReportStrategy
        strategy={strategy}
        language={reportLanguage}
        recommendedStrategy={report.dashboard?.coreConclusion?.recommendedStrategy}
      />

      {/* 投委会会议纪要 (Sprint 1B opt-in — renders null when committee is undefined) */}
      <CommitteeMinutesPanel committee={committee} language={reportLanguage} />

      {/* 结构化风险评估 (Sprint 4 opt-in — renders null when riskAssessment is undefined) */}
      <StructuredRiskCallout riskAssessment={riskAssessment} language={reportLanguage} />

      {/* 量化辅助信号 (Sprint 3) — silently renders null when no qlib data / no model */}
      {meta.stockCode && (
        <QuantContextPanel stockCode={meta.stockCode} language={reportLanguage} />
      )}

      {/* 复盘 / Decision Tracking — renders empty state when no journal entries exist */}
      {meta.stockCode && (
        <DecisionTrackingTab stockCode={meta.stockCode} language={reportLanguage} />
      )}

      {/* 资讯区 */}
      <ReportNews recordId={recordId} limit={8} language={reportLanguage} />

      {/* 透明度与追溯区 */}
      <ReportDetails details={details} recordId={recordId} language={reportLanguage} />

      {/* 分析模型标记（Issue #528）— 报告末尾 */}
      {shouldShowModel && (
        <p className="px-1 text-xs text-muted-text">
          {text.analysisModel}: {modelUsed}
        </p>
      )}
    </div>
  );
};
