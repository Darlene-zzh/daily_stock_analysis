import React, { useState } from 'react';
import type { ActionPlanItem, FactBundle } from '../../types/analysis';
import { EvidenceExpansion } from './EvidenceExpansion';

interface ActionPlanTableProps {
  items: ActionPlanItem[];
  /** Phase 5 — when present, expandable rows render an EvidenceExpansion under `evidenceRefs`. */
  bundle?: FactBundle | null;
}

const DIRECTION_CONFIG: Record<
  ActionPlanItem['direction'],
  { emoji: string; label: string; colorClass: string }
> = {
  buy: { emoji: '⬆️', label: '买入/加仓', colorClass: 'text-success' },
  sell: { emoji: '⬇️', label: '减仓', colorClass: 'text-warning' },
  stop_loss: { emoji: '🛑', label: '止损清仓', colorClass: 'text-danger' },
  take_profit: { emoji: '🎯', label: '止盈', colorClass: 'text-primary' },
};

const ORDINALS = ['①', '②', '③', '④'];

function PlanItemRow({
  item,
  index,
  bundle,
}: {
  item: ActionPlanItem;
  index: number;
  bundle?: FactBundle | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = DIRECTION_CONFIG[item.direction] ?? DIRECTION_CONFIG.buy;
  const ordinal = ORDINALS[index] ?? `(${index + 1})`;

  const posStr = [
    item.pctOfPosition != null ? `持仓 ${item.pctOfPosition.toFixed(1)}%` : null,
    // Use `!= null` (matches pctOfPosition) so 0.0% legitimately renders rather than
    // being hidden by `0` being falsy.
    item.pctOfEquity != null ? `权益 ${item.pctOfEquity.toFixed(1)}%` : null,
  ]
    .filter(Boolean)
    .join(' / ');

  const refs = item.evidenceRefs ?? [];
  const hasEvidence = refs.length > 0;
  const hasNarrative = Boolean(item.narrative && item.narrative.trim());
  const hasLegacyBasis = Boolean(
    item.technicalBasis || item.fundamentalBasis || item.quantSignal || item.invalidationRule,
  );
  const showExpandToggle = hasEvidence || hasNarrative || hasLegacyBasis;

  return (
    <div className="rounded-lg border border-subtle bg-surface/40 p-3">
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {ordinal} {cfg.emoji}{' '}
            <span className={cfg.colorClass}>{cfg.label}</span>
          </span>
          <span className="text-xs text-muted-text">优先级 {item.priority}</span>
          {item.tier === 'discipline_anchor' && (
            <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">
              📌 纪律锚
            </span>
          )}
          {item.provenance === 'synthesized' && (
            <span className="rounded bg-foreground/10 px-1.5 py-0.5 text-[10px] font-medium text-muted-text">
              🤖 代码兜底
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs">
          {item.triggerPrice != null && (
            <span className="text-foreground">
              触发价{' '}
              <span className="font-semibold">${item.triggerPrice.toFixed(2)}</span>
            </span>
          )}
          {item.shares != null && (
            <span className={`font-medium ${cfg.colorClass}`}>
              {/* Round fractional shares to 4 decimals for compact display; integer shares
                  render as-is via Number coercion. */}
              {Number.isInteger(item.shares) ? item.shares : item.shares.toFixed(4)} 股
              {posStr ? ` (${posStr})` : ''}
            </span>
          )}
        </div>
      </div>

      {/* Trigger condition */}
      <p className="mt-1 text-xs text-secondary-text">{item.triggerCondition}</p>

      {/* Expandable rationale toggle — only shown when there is content to reveal */}
      {showExpandToggle && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-accent-text hover:underline"
        >
          {expanded ? '▲ 收起分析依据' : '▼ 查看分析依据'}
        </button>
      )}

      {expanded && (
        <div className="mt-2 space-y-2 rounded bg-surface/60 p-2 text-xs text-secondary-text">
          {hasNarrative && (
            <p className="leading-relaxed text-foreground">{item.narrative}</p>
          )}
          {item.technicalBasis && (
            <p>
              <span className="font-medium text-foreground">技术面：</span>
              {item.technicalBasis}
            </p>
          )}
          {item.fundamentalBasis && (
            <p>
              <span className="font-medium text-foreground">基本面：</span>
              {item.fundamentalBasis}
            </p>
          )}
          {item.quantSignal && (
            <p>
              <span className="font-medium text-foreground">量化：</span>
              {item.quantSignal}
            </p>
          )}
          {item.invalidationRule && (
            <p>
              <span className="font-medium text-foreground">失效条件：</span>
              <span className="text-muted-text">{item.invalidationRule}</span>
            </p>
          )}
          {hasEvidence && bundle && (
            <EvidenceExpansion
              evidenceRefs={refs}
              bundle={bundle}
              groupBy="type"
              className="mt-1"
            />
          )}
        </div>
      )}
    </div>
  );
}

export const ActionPlanTable: React.FC<ActionPlanTableProps> = ({ items, bundle }) => {
  if (!items || items.length === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">📋 持仓操作计划</h3>
      <div className="space-y-2">
        {items.slice(0, 4).map((item, idx) => (
          <PlanItemRow key={idx} item={item} index={idx} bundle={bundle} />
        ))}
      </div>
    </div>
  );
};
