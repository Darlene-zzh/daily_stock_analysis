import React from 'react';
import type { PositionOutcomeSummary as POS } from '../../types/analysis';

interface PositionOutcomeSummaryProps {
  summary: POS;
}

export const PositionOutcomeSummary: React.FC<PositionOutcomeSummaryProps> = ({
  summary,
}) => {
  if (!summary || Object.keys(summary).length === 0) return null;
  const ccy = summary.worstCaseCurrency || '';
  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h4 className="text-sm font-semibold text-foreground">📊 仓位流水汇总</h4>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-muted-text">执行所有触发后剩余</p>
          <p className="font-mono text-foreground">
            {summary.remainingSharesAfterAllTriggers != null
              ? `${summary.remainingSharesAfterAllTriggers} 股`
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-muted-text">风险回报比</p>
          <p className="font-mono text-foreground">{summary.riskRewardRatio || '—'}</p>
        </div>
        <div>
          <p className="text-muted-text">最差止损</p>
          <p className="font-mono text-red-400">
            {summary.worstCaseLossAmount != null
              ? `${summary.worstCaseLossAmount} ${ccy}`
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-muted-text">最好止盈</p>
          <p className="font-mono text-emerald-400">
            {summary.bestCaseGainAmount != null
              ? `+${summary.bestCaseGainAmount} ${ccy}`
              : '—'}
          </p>
        </div>
      </div>
    </div>
  );
};
