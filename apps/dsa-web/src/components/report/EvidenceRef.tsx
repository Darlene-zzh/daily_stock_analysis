import clsx from 'clsx';
import type { FactRecord, CandidateLevel } from '../../types/analysis';

export interface EvidenceRefProps {
  /** Resolved fact (usually from `useFactBundle().getFact(id)`). When undefined, falls back to `fallbackId`. */
  fact: FactRecord | CandidateLevel | undefined;
  /** Raw fact_id used when the bundle lookup misses; surfaces a debuggable pill instead of disappearing silently. */
  fallbackId?: string;
  className?: string;
}

/**
 * Inline citation pill — renders the fact label as a small monospace chip,
 * with the human-readable display_value exposed via `aria-label` for assistive
 * tech. Native `title` hover tooltips are banned by the UI governance guard
 * (not keyboard/screen-reader accessible); a real tooltip popover can come later.
 */
export function EvidenceRef({ fact, fallbackId, className }: EvidenceRefProps) {
  if (!fact && !fallbackId) return null;

  const label = fact?.label ?? fallbackId ?? '';
  const tooltip = fact?.display_value ?? fallbackId ?? '';

  return (
    <span
      aria-label={tooltip}
      className={clsx(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5',
        'text-xs font-mono align-middle',
        'bg-slate-100 text-slate-700 hover:bg-slate-200',
        'dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700',
        className,
      )}
    >
      {label}
    </span>
  );
}
