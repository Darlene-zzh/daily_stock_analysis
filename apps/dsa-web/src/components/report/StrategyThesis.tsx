import React from 'react';

interface StrategyThesisProps {
  thesis: string;
  recommendedLabel?: string;
}

export const StrategyThesis: React.FC<StrategyThesisProps> = ({ thesis, recommendedLabel }) => {
  if (!thesis) return null;
  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h4 className="text-sm font-semibold text-foreground">
        🎯 AI 推荐策略{recommendedLabel ? `：${recommendedLabel}` : ''}
      </h4>
      <p className="text-sm leading-relaxed text-secondary-text">{thesis}</p>
    </div>
  );
};
