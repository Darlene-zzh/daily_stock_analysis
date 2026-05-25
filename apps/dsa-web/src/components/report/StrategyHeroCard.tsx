import React from 'react';
import type {
  FactBundle,
  StrategyChoice,
  StrategyThesisStructured,
} from '../../types/analysis';
import { useFactBundle } from '../../hooks/useFactBundle';
import { EvidenceRef } from './EvidenceRef';

interface StrategyHeroCardProps {
  choices: StrategyChoice[];
  recommendedId?: string;
  thesis?: string | StrategyThesisStructured;
  bundle?: FactBundle | null;
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

function labelOf(c: StrategyChoice): string {
  return c.labelZh || STRATEGY_LABEL[c.id] || c.id;
}
function emojiOf(c: StrategyChoice): string {
  return c.emoji || STRATEGY_EMOJI[c.id] || '📌';
}

function isStructuredThesis(t: unknown): t is StrategyThesisStructured {
  return typeof t === 'object' && t !== null && 'text' in t;
}

export const StrategyHeroCard: React.FC<StrategyHeroCardProps> = ({
  choices,
  recommendedId,
  thesis,
  bundle,
}) => {
  const { getFact } = useFactBundle(bundle);

  const recommended =
    recommendedId != null
      ? choices.find((c) => c.id === recommendedId && c.applicable !== false)
      : undefined;
  const alternatives = choices.filter(
    (c) => c.applicable !== false && c.id !== recommended?.id,
  );
  const inapplicable = choices.filter((c) => c.applicable === false);

  const thesisText = isStructuredThesis(thesis) ? thesis.text : thesis;
  const thesisRefs = isStructuredThesis(thesis) ? thesis.evidenceRefs : [];
  const thesisProvenance = isStructuredThesis(thesis) ? thesis.provenance : undefined;

  if (!recommended && alternatives.length === 0 && inapplicable.length === 0 && !thesisText) {
    return null;
  }

  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-3">
      {recommended && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-foreground">
              🎯 AI 推荐策略：{emojiOf(recommended)} {labelOf(recommended)}
            </h3>
            {thesisProvenance === 'synthesized' && (
              <span className="rounded bg-slate-500/15 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
                🤖 代码兜底
              </span>
            )}
          </div>
          {thesisText && (
            <p className="text-sm leading-relaxed text-secondary-text">{thesisText}</p>
          )}
          {thesisRefs.length > 0 && bundle && (
            <div className="flex flex-wrap gap-1.5">
              {thesisRefs.map((id) => (
                <EvidenceRef key={id} fact={getFact(id)} fallbackId={id} />
              ))}
            </div>
          )}
          {recommended.fitCondition && (
            <p className="text-xs text-muted-text">适用条件：{recommended.fitCondition}</p>
          )}
          {recommended.keyParams && (
            <p className="text-xs text-muted-text">关键参数：{recommended.keyParams}</p>
          )}
          {recommended.timeHorizon && (
            <p className="text-xs text-muted-text">⏱ {recommended.timeHorizon}</p>
          )}
        </div>
      )}

      {alternatives.length > 0 && (
        <div className="space-y-1.5 border-t border-subtle pt-3">
          <h4 className="text-xs font-medium text-muted-text">其他候选策略</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {alternatives.map((c) => (
              <div key={c.id} className="rounded-lg border border-subtle bg-surface/30 p-2 text-xs">
                <div className="font-medium text-foreground">
                  {emojiOf(c)} {labelOf(c)}
                </div>
                {c.fitCondition && (
                  <p className="mt-0.5 text-secondary-text">{c.fitCondition}</p>
                )}
                {c.timeHorizon && (
                  <p className="mt-0.5 text-muted-text">⏱ {c.timeHorizon}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {inapplicable.length > 0 && (
        <div className="space-y-1 border-t border-subtle pt-3">
          <h4 className="text-xs font-medium text-muted-text">不适用</h4>
          <ul className="space-y-0.5 text-xs text-muted-text">
            {inapplicable.map((c) => (
              <li key={c.id}>
                ⚪ {emojiOf(c)} {labelOf(c)}
                {c.inapplicableReason ? ` — ${c.inapplicableReason}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
