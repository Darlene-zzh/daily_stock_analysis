import React from 'react';
import type { ActionPlanItem, PositionOutcomeSummary } from '../../types/analysis';

interface PositionFlowTimelineProps {
  summary: PositionOutcomeSummary;
  triggers?: ActionPlanItem[];
}

const DIRECTION_EMOJI: Record<ActionPlanItem['direction'], string> = {
  buy: '⬆️',
  sell: '⬇️',
  stop_loss: '🛑',
  take_profit: '🎯',
};

function isEmpty(s: PositionOutcomeSummary): boolean {
  return (
    s == null ||
    Object.values(s).every((v) => v === null || v === undefined || v === '')
  );
}

export const PositionFlowTimeline: React.FC<PositionFlowTimelineProps> = ({
  summary,
  triggers = [],
}) => {
  if (isEmpty(summary) && triggers.length === 0) return null;
  const ccy = summary.worstCaseCurrency || '';
  const showGrid = !isEmpty(summary);

  const ordered = [...triggers].sort((a, b) => a.priority - b.priority);

  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-3">
      <h4 className="text-sm font-semibold text-foreground">📊 仓位流水汇总</h4>

      {ordered.length > 0 && (
        <ol className="space-y-1.5">
          {ordered.map((t, idx) => (
            <li
              key={idx}
              data-testid="flow-trigger-row"
              className="flex items-center gap-2 text-xs"
            >
              <span className="text-base">{DIRECTION_EMOJI[t.direction] ?? '•'}</span>
              <span className="font-mono text-foreground">${t.triggerPrice.toFixed(2)}</span>
              <span className="text-secondary-text">{t.triggerCondition}</span>
              {t.shares != null && (
                <span className="ml-auto text-muted-text">
                  {Number.isInteger(t.shares) ? t.shares : t.shares.toFixed(4)} 股
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      {showGrid && (
        <div className="grid grid-cols-2 gap-2 border-t border-subtle pt-3 text-xs">
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
            {/* A profit-protecting stop above cost yields a positive worst-case
                P&L — still a gain, so colour/sign by value rather than always
                painting "最差止损" red. */}
            <p
              className={`font-mono ${
                (summary.worstCaseLossAmount ?? 0) >= 0
                  ? 'text-success'
                  : 'text-danger'
              }`}
            >
              {summary.worstCaseLossAmount != null
                ? `${summary.worstCaseLossAmount >= 0 ? '+' : ''}${summary.worstCaseLossAmount} ${ccy}`.trim()
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-muted-text">最好止盈</p>
            <p className="font-mono text-success">
              {summary.bestCaseGainAmount != null
                ? `+${summary.bestCaseGainAmount} ${ccy}`.trim()
                : '—'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
