import React from 'react';
import type { StrategyChoice } from '../../types/analysis';

interface StrategySelectorProps {
  choices: StrategyChoice[];
  recommendedId?: string;
}

const STRATEGY_EMOJI: Record<string, string> = {
  long_term_hold: '🌳',
  swing_trade: '⚡',
  stepped_profit_taking: '🪜',
  wait_and_see: '🚪',
};
const STRATEGY_LABEL: Record<string, string> = {
  long_term_hold: '长线持有',
  swing_trade: '短线波段',
  stepped_profit_taking: '阶梯式止盈',
  wait_and_see: '暂不操作',
};

export const StrategySelector: React.FC<StrategySelectorProps> = ({
  choices,
  recommendedId,
}) => {
  if (!choices || choices.length === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">📌 策略选择</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {choices.map((c) => {
          const isRecommended = c.id === recommendedId;
          const emoji = c.emoji || STRATEGY_EMOJI[c.id] || '📌';
          const label = c.labelZh || STRATEGY_LABEL[c.id] || c.id;
          const baseClasses =
            'rounded-lg border p-3 text-xs space-y-1 transition-opacity';
          const stateClasses = !c.applicable
            ? 'border-subtle bg-surface/30 opacity-50'
            : isRecommended
              ? 'border-accent-text bg-accent-text/5 ring-2 ring-accent-text/30'
              : 'border-subtle bg-surface/50';

          return (
            <div key={c.id} className={`${baseClasses} ${stateClasses}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm text-foreground">
                  {emoji} {label}
                </span>
                {isRecommended && (
                  <span className="rounded bg-accent-text/20 px-1.5 py-0.5 text-[10px] font-medium text-accent-text">
                    AI 推荐
                  </span>
                )}
              </div>
              {!c.applicable && c.inapplicableReason && (
                <p className="text-muted-text">⚪ 不适用：{c.inapplicableReason}</p>
              )}
              {c.applicable && (
                <>
                  {c.fitCondition && <p className="text-secondary-text">{c.fitCondition}</p>}
                  {c.keyParams && (
                    <p className="text-secondary-text">
                      <span className="font-medium text-foreground">关键参数：</span>
                      {c.keyParams}
                    </p>
                  )}
                  {c.timeHorizon && (
                    <p className="text-muted-text">⏱ {c.timeHorizon}</p>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
