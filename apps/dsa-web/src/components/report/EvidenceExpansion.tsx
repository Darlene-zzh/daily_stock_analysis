import { useMemo, useState } from 'react';
import clsx from 'clsx';
import type { FactBundle } from '../../types/analysis';
import { useFactBundle } from '../../hooks/useFactBundle';
import { EvidenceRef } from './EvidenceRef';

export interface EvidenceExpansionProps {
  evidenceRefs: string[];
  bundle: FactBundle | null | undefined;
  groupBy?: 'type' | 'flat';
  defaultOpen?: string[];
  className?: string;
}

// Human labels for the group headers. Keep in sync with FactType in analysis.ts.
const GROUP_LABELS: Record<string, string> = {
  technical: '技术',
  committee: '委员会',
  intel: '情报',
  quant: '量化',
  portfolio: '持仓',
  flow: '资金流',
  chip: '筹码',
  candidate: '候选触发位',
};

function groupLabel(type: string): string {
  return GROUP_LABELS[type] ?? type;
}

export function EvidenceExpansion({
  evidenceRefs,
  bundle,
  groupBy = 'type',
  defaultOpen = [],
  className,
}: EvidenceExpansionProps) {
  const { getFact } = useFactBundle(bundle);
  const [openTypes, setOpenTypes] = useState<Set<string>>(
    () => new Set(defaultOpen),
  );

  const uniqueRefs = useMemo(() => {
    const seen = new Set<string>();
    return evidenceRefs.filter((id) => {
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }, [evidenceRefs]);

  const grouped = useMemo(() => {
    if (groupBy === 'flat') return null;
    const map = new Map<string, string[]>();
    for (const id of uniqueRefs) {
      const fact = getFact(id);
      const type = fact?.type ?? 'unknown';
      if (!map.has(type)) map.set(type, []);
      map.get(type)!.push(id);
    }
    return map;
  }, [uniqueRefs, getFact, groupBy]);

  if (!bundle || uniqueRefs.length === 0) return null;

  const toggle = (type: string) => {
    setOpenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (groupBy === 'flat') {
    return (
      <div className={clsx('flex flex-wrap gap-1.5', className)}>
        {uniqueRefs.map((id) => (
          <EvidenceRef key={id} fact={getFact(id)} fallbackId={id} />
        ))}
      </div>
    );
  }

  return (
    <div className={clsx('flex flex-col gap-2', className)}>
      {Array.from(grouped!.entries()).map(([type, ids]) => {
        const isOpen = openTypes.has(type);
        return (
          <div key={type} data-evidence-group={type} className="rounded border border-border">
            <button
              type="button"
              onClick={() => toggle(type)}
              aria-expanded={isOpen}
              className="w-full flex items-center justify-between px-3 py-1.5 text-sm font-medium hover:bg-hover"
            >
              <span>{groupLabel(type)}（{ids.length}）</span>
              <span aria-hidden>{isOpen ? '−' : '+'}</span>
            </button>
            {isOpen && (
              <div className="px-3 py-2 space-y-1.5 border-t border-border">
                {ids.map((id) => {
                  const fact = getFact(id);
                  return (
                    <div key={id} className="flex items-start gap-2 text-sm">
                      <EvidenceRef fact={fact} fallbackId={id} />
                      {fact && (
                        <span className="text-secondary-text">
                          {fact.display_value}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
