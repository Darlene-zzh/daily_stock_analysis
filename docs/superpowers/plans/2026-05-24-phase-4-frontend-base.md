# Phase 4 — Frontend Base + Quote Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Inline execution (no SDD dispatch) per [[feedback-subagent-prompt-size-limit]]. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the atomic frontend components (`useFactBundle`, `EvidenceRef`, `EvidenceExpansion`, `RefreshPriceButton`, `PriceMapCard`) plus a quote-fetch helper that consume `dashboard.fact_bundle` from Phase 1, so Phase 5 can wire them into the report page without any new low-level work. **Nothing built here is mounted in the existing UI.** The current `ReportSummary` / `ActionPlanTable` keep working unchanged.

**Architecture:** Pure additive — new TypeScript types for the already-shipped `dashboard.fact_bundle` payload, one Zustand-free hook (`useFactBundle`) that takes the dashboard slice as input and returns `getFact(id) → FactRecord | undefined`, and four presentational components that consume those types. All components default to "render nothing" when their inputs are missing so they can be safely dropped into pages whose data is partially populated. The refresh button calls the **already-existing** `GET /api/v1/stocks/{code}/quote` endpoint via a thin `stocksApi.getQuote` wrapper (no new backend route — see [Scope deviation](#scope-deviation-from-spec) below).

**Tech Stack:** TypeScript 5.9, React 19, Tailwind 4, Vitest 4, `@testing-library/react` 16, `@remixicon/react` (icons are already used elsewhere in the app), `clsx` + `tailwind-merge` (already in repo). No new dependencies.

**Reference spec:** [`docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md`](../specs/2026-05-21-evidence-grounded-decision-pipeline-design.md) Section C lines 485–563 (Frontend 组件清单 + API endpoint) + Section D lines 586–598 (前端测试).

**Pre-conditions:**
- PR #10 (`feat/committee-timeout-and-bilingual`) and PR #11 (`feat/phase-3-renderers`) **merged to `main`**. Until they merge, only the plan file is written — do not start coding.
- Branch: `feat/phase-4-frontend-base` cut from `main` after merges land.
- `dashboard.fact_bundle` is being attached by `src/core/pipeline.py::_attach_fact_bundle` (Phase 1, already shipped on `main` via PR #10). Sample shape lives at `src/core/pipeline.py:1876-1882`.
- `vitest run` baseline is green on `main` (verify with `cd apps/dsa-web && npm ci && npm run test` before starting).

---

## Scope deviation from spec

Spec Section C says "API 新增 endpoint" — create `api/v1/endpoints/quote.py` with a new `GET /quote/{code}`. **This plan does NOT do that** because `GET /api/v1/stocks/{code}/quote` (in [`api/v1/endpoints/stocks.py:242-296`](../../../api/v1/endpoints/stocks.py)) already returns `StockQuote(current_price, change_percent, update_time, ...)` and is wired through the same `StockService.get_realtime_quote → DataProvider` fallback chain that the spec endpoint would have used. Adding a parallel `/quote/{code}` would violate the AGENTS.md hard rule "优先复用现有模块……不新增平行实现".

Trade-off accepted:
- Spec asked for 1-second cache + 60 req/min rate limit. These are **not** implemented in this phase. If overload from the refresh button becomes a real issue, file a follow-up task to add caching + rate limiting **on the existing endpoint** rather than spinning up a duplicate.
- Spec's `quote` response shape (`{code, price, as_of, change_pct}`) is a subset of `StockQuote` — frontend will pick the fields it needs and ignore the rest.

---

## File Structure

**Modify:**
- `apps/dsa-web/src/types/analysis.ts` — append `FactRecord`, `CandidateLevel`, `FactBundle`, and extend `ActionPlanItem` with optional `evidence_refs`, `candidate_id`, `narrative`, `tier`, `provenance` (all optional, additive)
- `apps/dsa-web/src/api/stocks.ts` — add `stocksApi.getQuote(code)` method and `QuoteResponse` type

**Create:**
- `apps/dsa-web/src/hooks/useFactBundle.ts` — hook that takes `dashboard.fact_bundle` and returns `{ getFact, byType, byPrefix }`
- `apps/dsa-web/src/hooks/__tests__/useFactBundle.test.tsx`
- `apps/dsa-web/src/components/report/EvidenceRef.tsx` — inline pill that renders a fact_id; hover shows display_value
- `apps/dsa-web/src/components/report/__tests__/EvidenceRef.test.tsx`
- `apps/dsa-web/src/components/report/EvidenceExpansion.tsx` — collapsible group of evidence refs, optionally grouped by `type`
- `apps/dsa-web/src/components/report/__tests__/EvidenceExpansion.test.tsx`
- `apps/dsa-web/src/components/report/RefreshPriceButton.tsx` — small button that calls `stocksApi.getQuote(code)` and reports `{ price, asOf }`
- `apps/dsa-web/src/components/report/__tests__/RefreshPriceButton.test.tsx`
- `apps/dsa-web/src/components/report/PriceMapCard.tsx` — horizontal price-line with markers for each level + refresh button
- `apps/dsa-web/src/components/report/__tests__/PriceMapCard.test.tsx`

**Not touched in this phase:**
- `apps/dsa-web/src/components/report/ReportSummary.tsx`, `ActionPlanTable.tsx`, `StrategyThesis.tsx`, `PositionOutcomeSummary.tsx` (Phase 5 wires them)
- `api/v1/endpoints/*` (no new endpoint per [Scope deviation](#scope-deviation-from-spec))
- `src/notification.py`, `src/services/history_service.py`, `src/analysis/*` (PR #10/#11 territory; settled)

---

## Naming Conventions

TypeScript naming mirrors the Python dataclasses in [`src/analysis/facts.py:13-58`](../../../src/analysis/facts.py) — field names use snake_case in the JSON wire format because the backend serialises via `dataclasses.asdict` and the frontend is **camelCase-only at the boundary** when the API explicitly camelizes (e.g. `analysis.ts` uses camelcase-keys for analysis responses). For `fact_bundle` the backend emits raw snake_case (`src/core/pipeline.py:1876-1882`) and the frontend consumes it as-is in this phase. **Do not run `camelcase-keys` over `dashboard.fact_bundle`** — it would break consumer parity with the backend renderers built in Phase 3.

Type-name conventions:
- `FactRecord` — single fact (technical/committee/intel/portfolio/quant)
- `CandidateLevel` — candidate trigger price (extends FactRecord with `price`, `tier`, `direction`)
- `FactBundle` — top-level container (`as_of`, `market`, `stock_code`, `facts[]`, `candidates[]`)
- `QuoteResponse` — flat `{ stockCode, currentPrice, asOf, changePercent }` from `getQuote`

Component prop-shape conventions:
- All new components accept `className?: string` and forward via `clsx(props.className, ...)` so callers can override spacing
- All new components render `null` when required data is missing — no error UI, no spinner skeletons
- All new components are pure presentational (no Zustand store wiring) — Phase 5 wires them to `useHomeDashboardState`

---

### Task 1: TypeScript types for FactBundle

**Files:**
- Modify: `apps/dsa-web/src/types/analysis.ts` — append types at end of file

- [ ] **Step 1: Open the file and inspect the existing tail**

Run: `tail -40 apps/dsa-web/src/types/analysis.ts`
Expected: see the closing of the most recent type/interface so we know where to append.

- [ ] **Step 2: Append the new types**

Append at the end of `apps/dsa-web/src/types/analysis.ts`:

```typescript
// ============================================================
// Phase 1 FactBundle types (consumed in Phase 4+ frontend)
// Mirror src/analysis/facts.py — snake_case preserved at boundary
// ============================================================

export type FactType =
  | 'technical'
  | 'committee'
  | 'intel'
  | 'portfolio'
  | 'quant'
  | 'flow'
  | 'chip'
  | 'candidate';

export interface FactRecord {
  id: string;
  type: string; // FactType but kept loose for forward-compat
  label: string;
  value: unknown;
  display_value: string;
  unit?: string | null;
  source?: string;
  confidence?: number | null;
  as_of?: string | null;
  extra?: Record<string, unknown>;
}

export type CandidateDirection =
  | 'entry'
  | 'exit'
  | 'stop'
  | 'take_profit'
  | 'stop_loss';

export type CandidateTier =
  | 'primary'
  | 'secondary'
  | 'discipline_anchor'
  | 'filtered';

export interface CandidateLevel extends FactRecord {
  direction: CandidateDirection;
  price: number;
  basis_fact_id: string;
  basis_rule: string;
  applicable_strategies: string[];
  tier: CandidateTier;
  distance_pct_from_current: number;
}

export interface FactBundle {
  as_of: string;
  market: 'a' | 'hk' | 'us';
  stock_code: string;
  facts: FactRecord[];
  candidates: CandidateLevel[];
}

// ActionPlanItem Phase 2 fields — additive, all optional
// (the existing ActionPlanItem may not yet declare these; if it does,
// fold these into the existing interface rather than re-declaring)
export interface ActionPlanItemEvidenceFields {
  candidate_id?: string | null;
  evidence_refs?: string[];
  narrative?: string | null;
  tier?: CandidateTier;
  provenance?: 'llm' | 'synthesized' | null;
}
```

- [ ] **Step 3: Reconcile with existing `ActionPlanItem`**

Run: `grep -n "ActionPlanItem" apps/dsa-web/src/types/analysis.ts`

If an `ActionPlanItem` interface already exists in this file, **modify it in place** to add the five fields above as optional members rather than leaving the trailing `ActionPlanItemEvidenceFields` orphan. If it does not, leave `ActionPlanItemEvidenceFields` standalone — Phase 5 will fold it into the real interface when it's created.

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd apps/dsa-web && npx tsc --noEmit`
Expected: zero errors. (If the existing file has unrelated errors, that's a pre-existing baseline issue — note in the task log and continue.)

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/types/analysis.ts
git commit -m "feat(types): add FactBundle/FactRecord/CandidateLevel for Phase 4 frontend"
```

---

### Task 2: `useFactBundle` hook + tests

**Files:**
- Create: `apps/dsa-web/src/hooks/useFactBundle.ts`
- Create: `apps/dsa-web/src/hooks/__tests__/useFactBundle.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/hooks/__tests__/useFactBundle.test.tsx`:

```typescript
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useFactBundle } from '../useFactBundle';
import type { FactBundle } from '../../types/analysis';

const sampleBundle: FactBundle = {
  as_of: '2026-05-24T10:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    {
      id: 'technical.resistance',
      type: 'technical',
      label: '阻力位',
      value: 226.13,
      display_value: '$226.13',
    },
    {
      id: 'technical.rsi_12',
      type: 'technical',
      label: 'RSI(12)',
      value: 71.1,
      display_value: 'RSI(12) = 71.1 (超买)',
    },
    {
      id: 'committee.pm_verdict',
      type: 'committee',
      label: 'PM 裁决',
      value: 'hold',
      display_value: 'PM hold (5.8/10)',
    },
  ],
  candidates: [
    {
      id: 'candidate.resistance_take_profit',
      type: 'candidate',
      label: '阻力位止盈',
      value: 226.13,
      display_value: '$226.13',
      direction: 'take_profit',
      price: 226.13,
      basis_fact_id: 'technical.resistance',
      basis_rule: 'resistance_touch',
      applicable_strategies: ['short_term', 'swing'],
      tier: 'primary',
      distance_pct_from_current: 2.3,
    },
  ],
};

describe('useFactBundle', () => {
  it('returns undefined for getFact when bundle is null', () => {
    const { result } = renderHook(() => useFactBundle(null));
    expect(result.current.getFact('technical.resistance')).toBeUndefined();
    expect(result.current.byType('technical')).toEqual([]);
    expect(result.current.byPrefix('technical.')).toEqual([]);
  });

  it('returns undefined for getFact when bundle is undefined', () => {
    const { result } = renderHook(() => useFactBundle(undefined));
    expect(result.current.getFact('technical.resistance')).toBeUndefined();
  });

  it('resolves a fact by id', () => {
    const { result } = renderHook(() => useFactBundle(sampleBundle));
    const fact = result.current.getFact('technical.resistance');
    expect(fact?.display_value).toBe('$226.13');
  });

  it('resolves a candidate by id (candidates are in the same lookup space)', () => {
    const { result } = renderHook(() => useFactBundle(sampleBundle));
    const cand = result.current.getFact('candidate.resistance_take_profit');
    expect(cand?.display_value).toBe('$226.13');
    // CandidateLevel-specific field still accessible via cast
    expect((cand as { price?: number })?.price).toBe(226.13);
  });

  it('returns undefined for an unknown id (no throw)', () => {
    const { result } = renderHook(() => useFactBundle(sampleBundle));
    expect(result.current.getFact('does.not.exist')).toBeUndefined();
  });

  it('byType returns only facts whose type matches exactly', () => {
    const { result } = renderHook(() => useFactBundle(sampleBundle));
    const tech = result.current.byType('technical');
    expect(tech.map((f) => f.id)).toEqual([
      'technical.resistance',
      'technical.rsi_12',
    ]);
  });

  it('byPrefix returns facts whose id starts with the prefix (candidates included)', () => {
    const { result } = renderHook(() => useFactBundle(sampleBundle));
    const all = result.current.byPrefix('technical.');
    expect(all.map((f) => f.id).sort()).toEqual([
      'technical.resistance',
      'technical.rsi_12',
    ]);
    const cands = result.current.byPrefix('candidate.');
    expect(cands).toHaveLength(1);
  });

  it('memoizes the lookup map across renders with the same bundle reference', () => {
    const { result, rerender } = renderHook(({ b }) => useFactBundle(b), {
      initialProps: { b: sampleBundle },
    });
    const first = result.current.getFact;
    rerender({ b: sampleBundle });
    expect(result.current.getFact).toBe(first); // referential equality on same input
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/hooks/__tests__/useFactBundle.test.tsx`
Expected: FAIL with `Cannot find module '../useFactBundle'`.

- [ ] **Step 3: Implement the hook**

Create `apps/dsa-web/src/hooks/useFactBundle.ts`:

```typescript
import { useMemo } from 'react';
import type { FactBundle, FactRecord, CandidateLevel } from '../types/analysis';

export interface UseFactBundleResult {
  /** Map a fact_id (or candidate_id) to its FactRecord. Returns undefined when unknown or when bundle is empty. */
  getFact: (id: string) => FactRecord | CandidateLevel | undefined;
  /** All facts whose `type` matches the argument exactly. */
  byType: (type: string) => FactRecord[];
  /** All facts whose `id` starts with the prefix (candidates included). */
  byPrefix: (prefix: string) => Array<FactRecord | CandidateLevel>;
}

const EMPTY_FACTS: FactRecord[] = [];
const EMPTY_MIXED: Array<FactRecord | CandidateLevel> = [];

/**
 * Build a fast lookup over a FactBundle. The lookup is memoized on the bundle
 * reference — passing the same object across renders returns the same fns.
 *
 * Pass `null` or `undefined` when the dashboard has no `fact_bundle` field
 * (e.g. legacy reports). All accessors degrade to empty / undefined.
 */
export function useFactBundle(
  bundle: FactBundle | null | undefined,
): UseFactBundleResult {
  return useMemo(() => {
    if (!bundle) {
      return {
        getFact: () => undefined,
        byType: () => EMPTY_FACTS,
        byPrefix: () => EMPTY_MIXED,
      };
    }

    const lookup = new Map<string, FactRecord | CandidateLevel>();
    for (const f of bundle.facts) lookup.set(f.id, f);
    for (const c of bundle.candidates) lookup.set(c.id, c);

    return {
      getFact: (id: string) => lookup.get(id),
      byType: (type: string) => bundle.facts.filter((f) => f.type === type),
      byPrefix: (prefix: string) => {
        const out: Array<FactRecord | CandidateLevel> = [];
        for (const f of bundle.facts) if (f.id.startsWith(prefix)) out.push(f);
        for (const c of bundle.candidates) if (c.id.startsWith(prefix)) out.push(c);
        return out;
      },
    };
  }, [bundle]);
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/hooks/__tests__/useFactBundle.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/hooks/useFactBundle.ts apps/dsa-web/src/hooks/__tests__/useFactBundle.test.tsx
git commit -m "feat(hooks): useFactBundle — lookup facts/candidates from dashboard.fact_bundle"
```

---

### Task 3: `EvidenceRef` component + tests

**Files:**
- Create: `apps/dsa-web/src/components/report/EvidenceRef.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/EvidenceRef.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/EvidenceRef.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceRef } from '../EvidenceRef';
import type { FactRecord } from '../../../types/analysis';

const sampleFact: FactRecord = {
  id: 'technical.resistance',
  type: 'technical',
  label: '阻力位',
  value: 226.13,
  display_value: '$226.13',
  source: 'data_perspective.technical',
};

describe('EvidenceRef', () => {
  it('renders a pill with the fact label', () => {
    render(<EvidenceRef fact={sampleFact} />);
    expect(screen.getByText('阻力位')).toBeInTheDocument();
  });

  it('exposes display_value in a title attribute for hover tooltip', () => {
    render(<EvidenceRef fact={sampleFact} />);
    const pill = screen.getByText('阻力位');
    expect(pill.closest('[title]')).toHaveAttribute('title', '$226.13');
  });

  it('renders nothing when fact is undefined', () => {
    const { container } = render(<EvidenceRef fact={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('accepts a fallback id when fact is missing but id is known', () => {
    const { container } = render(
      <EvidenceRef fact={undefined} fallbackId="quant.score" />,
    );
    // Fallback renders the raw id so reviewers can see what's referenced
    expect(container.textContent).toContain('quant.score');
  });

  it('forwards className to the root element', () => {
    const { container } = render(
      <EvidenceRef fact={sampleFact} className="custom-pill" />,
    );
    expect(container.querySelector('.custom-pill')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/EvidenceRef.test.tsx`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the component**

Create `apps/dsa-web/src/components/report/EvidenceRef.tsx`:

```typescript
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
 * with the human-readable display_value exposed via `title` for hover. Phase 4
 * keeps interaction minimal; Phase 5 may swap to a tooltip popover.
 */
export function EvidenceRef({ fact, fallbackId, className }: EvidenceRefProps) {
  if (!fact && !fallbackId) return null;

  const label = fact?.label ?? fallbackId ?? '';
  const tooltip = fact?.display_value ?? fallbackId ?? '';

  return (
    <span
      title={tooltip}
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/EvidenceRef.test.tsx`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/EvidenceRef.tsx apps/dsa-web/src/components/report/__tests__/EvidenceRef.test.tsx
git commit -m "feat(report): EvidenceRef — inline citation pill for fact lookups"
```

---

### Task 4: `EvidenceExpansion` component + tests

**Files:**
- Create: `apps/dsa-web/src/components/report/EvidenceExpansion.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/EvidenceExpansion.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/EvidenceExpansion.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceExpansion } from '../EvidenceExpansion';
import type { FactBundle } from '../../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-24T10:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    {
      id: 'technical.resistance',
      type: 'technical',
      label: '阻力位',
      value: 226.13,
      display_value: '$226.13 阻力位',
    },
    {
      id: 'technical.rsi_12',
      type: 'technical',
      label: 'RSI(12)',
      value: 71.1,
      display_value: 'RSI(12) = 71.1 (超买)',
    },
    {
      id: 'committee.pm_verdict',
      type: 'committee',
      label: 'PM 裁决',
      value: 'hold',
      display_value: 'PM hold (5.8/10)',
    },
    {
      id: 'quant.score',
      type: 'quant',
      label: '量化评分',
      value: 0.62,
      display_value: '量化评分 0.62',
    },
  ],
  candidates: [],
};

describe('EvidenceExpansion', () => {
  it('renders nothing when evidenceRefs is empty', () => {
    const { container } = render(
      <EvidenceExpansion evidenceRefs={[]} bundle={bundle} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when bundle is missing', () => {
    const { container } = render(
      <EvidenceExpansion evidenceRefs={['technical.rsi_12']} bundle={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('groups refs by type when groupBy="type" (default)', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={[
          'technical.rsi_12',
          'committee.pm_verdict',
          'technical.resistance',
        ]}
        bundle={bundle}
      />,
    );
    // Two group headers visible
    expect(screen.getByText(/技术/i)).toBeInTheDocument();
    expect(screen.getByText(/委员会/i)).toBeInTheDocument();
  });

  it('renders refs flat when groupBy="flat"', () => {
    const { container } = render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'committee.pm_verdict']}
        bundle={bundle}
        groupBy="flat"
      />,
    );
    // No group headers; pills appear sequentially
    expect(container.querySelectorAll('[data-evidence-group]').length).toBe(0);
  });

  it('expands a group when its header is clicked', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12']}
        bundle={bundle}
      />,
    );
    const header = screen.getByRole('button', { name: /技术/i });
    // Default collapsed — display_value not visible
    expect(screen.queryByText('RSI(12) = 71.1 (超买)')).not.toBeInTheDocument();
    fireEvent.click(header);
    expect(screen.getByText('RSI(12) = 71.1 (超买)')).toBeInTheDocument();
  });

  it('respects defaultOpen prop', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12']}
        bundle={bundle}
        defaultOpen={['technical']}
      />,
    );
    expect(screen.getByText('RSI(12) = 71.1 (超买)')).toBeInTheDocument();
  });

  it('renders a fallback pill for refs that miss the bundle', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'unknown.fact_id']}
        bundle={bundle}
        defaultOpen={['technical', 'unknown']}
      />,
    );
    expect(screen.getByText(/unknown.fact_id/)).toBeInTheDocument();
  });

  it('dedupes repeated refs', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'technical.rsi_12']}
        bundle={bundle}
        defaultOpen={['technical']}
      />,
    );
    const pills = screen.getAllByText('RSI(12)');
    expect(pills).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/EvidenceExpansion.test.tsx`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the component**

Create `apps/dsa-web/src/components/report/EvidenceExpansion.tsx`:

```typescript
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
          <div key={type} data-evidence-group={type} className="rounded border border-slate-200 dark:border-slate-700">
            <button
              type="button"
              onClick={() => toggle(type)}
              aria-expanded={isOpen}
              className="w-full flex items-center justify-between px-3 py-1.5 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span>{groupLabel(type)}（{ids.length}）</span>
              <span aria-hidden>{isOpen ? '−' : '+'}</span>
            </button>
            {isOpen && (
              <div className="px-3 py-2 space-y-1.5 border-t border-slate-100 dark:border-slate-800">
                {ids.map((id) => {
                  const fact = getFact(id);
                  return (
                    <div key={id} className="flex items-start gap-2 text-sm">
                      <EvidenceRef fact={fact} fallbackId={id} />
                      {fact && (
                        <span className="text-slate-600 dark:text-slate-300">
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/EvidenceExpansion.test.tsx`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/EvidenceExpansion.tsx apps/dsa-web/src/components/report/__tests__/EvidenceExpansion.test.tsx
git commit -m "feat(report): EvidenceExpansion — collapsible grouped evidence panel"
```

---

### Task 5: `stocksApi.getQuote` helper + test

**Files:**
- Modify: `apps/dsa-web/src/api/stocks.ts` — append `getQuote` method and `QuoteResponse` type
- Create: `apps/dsa-web/src/api/__tests__/stocks.test.ts` (only if absent; otherwise extend it)

- [ ] **Step 1: Check whether `apps/dsa-web/src/api/__tests__/stocks.test.ts` exists**

Run: `ls apps/dsa-web/src/api/__tests__/stocks.test.ts 2>/dev/null || echo MISSING`

If MISSING: create a new file in Step 2. Otherwise: append the new describe block at the end.

- [ ] **Step 2: Write the failing test**

Either create or append to `apps/dsa-web/src/api/__tests__/stocks.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { stocksApi } from '../stocks';
import apiClient from '../index';

vi.mock('../index', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
    },
  };
});

describe('stocksApi.getQuote', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('GETs /api/v1/stocks/{code}/quote and maps to camelCase', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        stock_code: 'NVDA',
        stock_name: 'NVIDIA',
        current_price: 226.13,
        change_percent: 1.23,
        update_time: '2026-05-24T10:00:00Z',
      },
    });

    const quote = await stocksApi.getQuote('NVDA');

    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/stocks/NVDA/quote');
    expect(quote).toEqual({
      stockCode: 'NVDA',
      stockName: 'NVIDIA',
      currentPrice: 226.13,
      changePercent: 1.23,
      asOf: '2026-05-24T10:00:00Z',
    });
  });

  it('throws when the response is missing current_price', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { stock_code: 'NVDA' },
    });
    await expect(stocksApi.getQuote('NVDA')).rejects.toThrow();
  });

  it('encodes the stock code into the URL path', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { stock_code: 'hk00700', current_price: 350.5, update_time: '2026-05-24T10:00:00Z' },
    });
    await stocksApi.getQuote('hk00700');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/stocks/hk00700/quote');
  });
});
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/api/__tests__/stocks.test.ts`
Expected: FAIL with `stocksApi.getQuote is not a function`.

- [ ] **Step 4: Implement the helper**

Append to `apps/dsa-web/src/api/stocks.ts` (inside the `stocksApi` object literal, before the closing `};`):

```typescript
  async getQuote(stockCode: string): Promise<QuoteResponse> {
    const response = await apiClient.get(`/api/v1/stocks/${stockCode}/quote`);
    const data = response.data as {
      stock_code?: string;
      stock_name?: string | null;
      current_price?: number;
      change_percent?: number | null;
      update_time?: string;
    };
    if (typeof data.current_price !== 'number') {
      throw new Error(`getQuote(${stockCode}): missing current_price in response`);
    }
    return {
      stockCode: data.stock_code ?? stockCode,
      stockName: data.stock_name ?? null,
      currentPrice: data.current_price,
      changePercent: data.change_percent ?? null,
      asOf: data.update_time ?? new Date().toISOString(),
    };
  },
```

And add the type near the top of the file (after the existing `ExtractItem` / `ExtractFromImageResponse` types):

```typescript
export type QuoteResponse = {
  stockCode: string;
  stockName: string | null;
  currentPrice: number;
  changePercent: number | null;
  asOf: string; // ISO timestamp
};
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/api/__tests__/stocks.test.ts`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add apps/dsa-web/src/api/stocks.ts apps/dsa-web/src/api/__tests__/stocks.test.ts
git commit -m "feat(api): stocksApi.getQuote — typed wrapper over existing /quote endpoint"
```

---

### Task 6: `RefreshPriceButton` component + tests

**Files:**
- Create: `apps/dsa-web/src/components/report/RefreshPriceButton.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/RefreshPriceButton.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/RefreshPriceButton.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { RefreshPriceButton } from '../RefreshPriceButton';
import { stocksApi } from '../../../api/stocks';

vi.mock('../../../api/stocks', () => ({
  stocksApi: {
    getQuote: vi.fn(),
  },
}));

describe('RefreshPriceButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an enabled button by default', () => {
    render(<RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} />);
    expect(screen.getByRole('button', { name: /刷新/i })).toBeEnabled();
  });

  it('calls stocksApi.getQuote with the stock code on click', async () => {
    const user = userEvent.setup();
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stockCode: 'NVDA',
      currentPrice: 226.13,
      asOf: '2026-05-24T10:00:00Z',
    });
    const onQuote = vi.fn();
    render(<RefreshPriceButton stockCode="NVDA" onQuote={onQuote} />);

    await user.click(screen.getByRole('button', { name: /刷新/i }));

    await waitFor(() => {
      expect(stocksApi.getQuote).toHaveBeenCalledWith('NVDA');
      expect(onQuote).toHaveBeenCalledWith({
        price: 226.13,
        asOf: '2026-05-24T10:00:00Z',
      });
    });
  });

  it('shows loading state while the request is in flight', async () => {
    const user = userEvent.setup();
    let resolveFn: ((value: unknown) => void) | undefined;
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFn = resolve;
      }),
    );
    render(<RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /刷新/i }));
    expect(screen.getByRole('button')).toBeDisabled();

    resolveFn!({
      stockCode: 'NVDA',
      currentPrice: 226.13,
      asOf: '2026-05-24T10:00:00Z',
    });
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());
  });

  it('exposes an error to onError callback when the request fails', async () => {
    const user = userEvent.setup();
    const err = new Error('boom');
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockRejectedValueOnce(err);
    const onError = vi.fn();
    render(
      <RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} onError={onError} />,
    );
    await user.click(screen.getByRole('button', { name: /刷新/i }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(err));
  });

  it('does not call onQuote when the request fails', async () => {
    const user = userEvent.setup();
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('boom'),
    );
    const onQuote = vi.fn();
    render(
      <RefreshPriceButton stockCode="NVDA" onQuote={onQuote} onError={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: /刷新/i }));
    await waitFor(() => expect(onQuote).not.toHaveBeenCalled());
  });

  it('renders nothing when stockCode is empty', () => {
    const { container } = render(
      <RefreshPriceButton stockCode="" onQuote={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Check whether `@testing-library/user-event` is installed**

Run: `cd apps/dsa-web && node -e "console.log(require('./package.json').devDependencies['@testing-library/user-event'] || 'MISSING')"`

If MISSING: install it as a devDependency:

```bash
cd apps/dsa-web && npm install --save-dev @testing-library/user-event@^14
```

Then commit the `package.json` + `package-lock.json` deltas at the end of this task alongside the component changes.

- [ ] **Step 3: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/RefreshPriceButton.test.tsx`
Expected: FAIL with module-not-found.

- [ ] **Step 4: Implement the component**

Create `apps/dsa-web/src/components/report/RefreshPriceButton.tsx`:

```typescript
import { useState } from 'react';
import clsx from 'clsx';
import { RiRefreshLine } from '@remixicon/react';
import { stocksApi } from '../../api/stocks';

export interface RefreshPriceButtonProps {
  stockCode: string;
  onQuote: (quote: { price: number; asOf: string }) => void;
  onError?: (err: unknown) => void;
  className?: string;
}

export function RefreshPriceButton({
  stockCode,
  onQuote,
  onError,
  className,
}: RefreshPriceButtonProps) {
  const [loading, setLoading] = useState(false);

  if (!stockCode) return null;

  const handleClick = async () => {
    setLoading(true);
    try {
      const q = await stocksApi.getQuote(stockCode);
      onQuote({ price: q.currentPrice, asOf: q.asOf });
    } catch (err) {
      onError?.(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      className={clsx(
        'inline-flex items-center gap-1 rounded border px-2 py-1 text-xs',
        'border-slate-300 bg-white hover:bg-slate-50',
        'dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className,
      )}
      aria-label="刷新当前价"
    >
      <RiRefreshLine size={14} className={clsx(loading && 'animate-spin')} />
      <span>{loading ? '刷新中…' : '刷新价格'}</span>
    </button>
  );
}
```

If `@remixicon/react` does not expose `RiRefreshLine` (check Step 2 grep output for what is actually imported in the codebase today), substitute the icon used in the existing components — `lucide-react`'s `RefreshCw` is also already in `package.json`.

- [ ] **Step 5: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/RefreshPriceButton.test.tsx`
Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add apps/dsa-web/src/components/report/RefreshPriceButton.tsx apps/dsa-web/src/components/report/__tests__/RefreshPriceButton.test.tsx
# Include package.json/lock if @testing-library/user-event was newly installed:
# git add apps/dsa-web/package.json apps/dsa-web/package-lock.json
git commit -m "feat(report): RefreshPriceButton — calls stocksApi.getQuote on click"
```

---

### Task 7: `PriceMapCard` component + tests

**Files:**
- Create: `apps/dsa-web/src/components/report/PriceMapCard.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/PriceMapCard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/PriceMapCard.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PriceMapCard } from '../PriceMapCard';

const baseLevels = [
  { factId: 'technical.support', price: 215.5, label: '支撑', color: 'green' as const, role: 'support' as const },
  { factId: 'technical.resistance', price: 226.13, label: '阻力', color: 'red' as const, role: 'resistance' as const },
  { factId: 'technical.ma20', price: 220.0, label: 'MA20', color: 'blue' as const, role: 'ma' as const },
];

describe('PriceMapCard', () => {
  it('renders nothing when levels is empty', () => {
    const { container } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={[]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the current price prominently', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    expect(screen.getByText(/220\.5/)).toBeInTheDocument();
  });

  it('renders a marker per level with its label', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    for (const lvl of baseLevels) {
      expect(screen.getByText(lvl.label)).toBeInTheDocument();
    }
  });

  it('renders distance % from current price for each level', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    // Resistance is +2.55% (226.13 vs 220.5)
    expect(screen.getByText(/\+2\.5\d%/)).toBeInTheDocument();
    // Support is -2.27% (215.5 vs 220.5)
    expect(screen.getByText(/-2\.2\d%/)).toBeInTheDocument();
  });

  it('renders the RefreshPriceButton when onRefresh is not provided', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    // Default refresh button (uses stocksApi)
    expect(screen.getByRole('button', { name: /刷新/i })).toBeInTheDocument();
  });

  it('calls the supplied onRefresh callback and updates displayed price', async () => {
    const onRefresh = vi.fn().mockResolvedValue({ price: 222.0, asOf: '2026-05-24T11:00:00Z' });
    const { findByText, getByRole } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
        onRefresh={onRefresh}
      />,
    );
    getByRole('button', { name: /刷新/i }).click();
    expect(onRefresh).toHaveBeenCalled();
    // After refresh, displayed price updates to 222.0
    expect(await findByText(/222(\.|0)/)).toBeInTheDocument();
  });

  it('renders nothing when currentPrice is 0 or negative (invalid input)', () => {
    const { container } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={0}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/PriceMapCard.test.tsx`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the component**

Create `apps/dsa-web/src/components/report/PriceMapCard.tsx`:

```typescript
import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { RefreshPriceButton } from './RefreshPriceButton';

export type PriceMapColor = 'red' | 'green' | 'orange' | 'blue' | 'gray';
export type PriceMapRole = 'support' | 'resistance' | 'stop' | 'target' | 'ma';

export interface PriceMapLevel {
  factId: string;
  price: number;
  label: string;
  color: PriceMapColor;
  role: PriceMapRole;
}

export interface PriceMapCardProps {
  stockCode: string;
  currentPrice: number;
  currentPriceAsOf: string;
  levels: PriceMapLevel[];
  /** Optional override; when omitted, the card calls stocksApi.getQuote via the embedded RefreshPriceButton. */
  onRefresh?: () => Promise<{ price: number; asOf: string }>;
  className?: string;
}

const COLOR_TO_CLASS: Record<PriceMapColor, string> = {
  red: 'bg-red-500 text-red-700 border-red-300',
  green: 'bg-green-500 text-green-700 border-green-300',
  orange: 'bg-orange-500 text-orange-700 border-orange-300',
  blue: 'bg-blue-500 text-blue-700 border-blue-300',
  gray: 'bg-slate-500 text-slate-700 border-slate-300',
};

function distancePct(level: number, current: number): number {
  if (current <= 0) return 0;
  return ((level - current) / current) * 100;
}

function formatPct(pct: number): string {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

export function PriceMapCard({
  stockCode,
  currentPrice,
  currentPriceAsOf,
  levels,
  onRefresh,
  className,
}: PriceMapCardProps) {
  const [displayPrice, setDisplayPrice] = useState(currentPrice);
  const [displayAsOf, setDisplayAsOf] = useState(currentPriceAsOf);

  const sortedLevels = useMemo(
    () => [...levels].sort((a, b) => a.price - b.price),
    [levels],
  );

  if (currentPrice <= 0 || levels.length === 0) return null;

  // Project levels + currentPrice onto a horizontal axis. We compute a min/max
  // padded by 5% so endpoints don't sit on the card edge.
  const allPrices = [displayPrice, ...sortedLevels.map((l) => l.price)];
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const padding = (maxP - minP) * 0.05 || maxP * 0.01;
  const axisMin = minP - padding;
  const axisMax = maxP + padding;
  const project = (p: number) =>
    ((p - axisMin) / (axisMax - axisMin)) * 100;

  const handleQuote = (q: { price: number; asOf: string }) => {
    setDisplayPrice(q.price);
    setDisplayAsOf(q.asOf);
  };

  // When the caller supplies onRefresh, wrap it so the card's state still updates.
  const refreshButton = onRefresh ? (
    <button
      type="button"
      onClick={async () => {
        const q = await onRefresh();
        handleQuote(q);
      }}
      className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
      aria-label="刷新当前价"
    >
      <span>刷新价格</span>
    </button>
  ) : (
    <RefreshPriceButton stockCode={stockCode} onQuote={handleQuote} />
  );

  return (
    <div
      className={clsx(
        'rounded-lg border border-slate-200 dark:border-slate-700',
        'bg-white dark:bg-slate-900 p-4',
        className,
      )}
      data-component="price-map-card"
    >
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">当前价</div>
          <div className="text-2xl font-semibold tabular-nums">
            {displayPrice.toFixed(2)}
          </div>
          <div className="text-xs text-slate-400">{displayAsOf}</div>
        </div>
        {refreshButton}
      </div>

      <div className="relative h-12 mt-6">
        <div className="absolute inset-x-0 top-1/2 h-px bg-slate-200 dark:bg-slate-700" />
        {/* Current-price marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-slate-900 dark:bg-slate-100 ring-2 ring-white dark:ring-slate-900"
          style={{ left: `${project(displayPrice)}%` }}
          aria-label={`当前价 ${displayPrice.toFixed(2)}`}
        />
        {/* Level markers */}
        {sortedLevels.map((lvl, idx) => {
          const pct = distancePct(lvl.price, displayPrice);
          // Alternate label position above/below to reduce overlap
          const labelAbove = idx % 2 === 0;
          return (
            <div
              key={lvl.factId}
              className="absolute top-1/2"
              style={{ left: `${project(lvl.price)}%` }}
            >
              <div
                className={clsx(
                  'absolute -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full',
                  COLOR_TO_CLASS[lvl.color].split(' ')[0],
                )}
              />
              <div
                className={clsx(
                  'absolute -translate-x-1/2 whitespace-nowrap text-xs leading-tight',
                  labelAbove ? 'bottom-4' : 'top-4',
                )}
              >
                <div className={clsx('font-medium', COLOR_TO_CLASS[lvl.color].split(' ')[1])}>
                  {lvl.label}
                </div>
                <div className="text-slate-400 tabular-nums">
                  {lvl.price.toFixed(2)} · {formatPct(pct)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/dsa-web && npm run test -- src/components/report/__tests__/PriceMapCard.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the full apps/dsa-web test suite + lint + build to catch regressions**

Run in sequence:

```bash
cd apps/dsa-web
npm run test
npm run lint
npm run build
```

Expected:
- `npm run test` — all green; new files contribute ~36 added tests (7+5+8+3+6+7)
- `npm run lint` — clean; if eslint flags unused imports or `any` casts in the new files, fix in-place and re-run
- `npm run build` — clean; tsc -b must produce zero errors. If it complains about `FactRecord` / `CandidateLevel` shapes anywhere in the existing code (it shouldn't — they're additive), inspect the caller and decide whether to widen the type or revert

- [ ] **Step 6: Commit**

```bash
git add apps/dsa-web/src/components/report/PriceMapCard.tsx apps/dsa-web/src/components/report/__tests__/PriceMapCard.test.tsx
git commit -m "feat(report): PriceMapCard — horizontal price-line with level markers + refresh"
```

---

### Task 8: PR description + open PR

**Files:**
- No code changes; just open the PR with a description that meets the PR template.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/phase-4-frontend-base
```

- [ ] **Step 2: Open the PR**

Since `gh` is not installed on this machine (per [[repo-conventions]]), open the PR via the GitHub web UI with this body:

```markdown
## 改了什么
Phase 4 of the evidence-grounded decision pipeline — frontend base. Adds atomic, presentational components that Phase 5 will mount into the report page. **Nothing in this PR is visible in the existing UI** (no `ReportSummary` changes).

New code:
- `apps/dsa-web/src/types/analysis.ts` — added `FactRecord` / `CandidateLevel` / `FactBundle` types (mirror `src/analysis/facts.py`)
- `apps/dsa-web/src/hooks/useFactBundle.ts` — `getFact(id)` / `byType` / `byPrefix` lookup
- `apps/dsa-web/src/components/report/EvidenceRef.tsx` — inline citation pill
- `apps/dsa-web/src/components/report/EvidenceExpansion.tsx` — collapsible grouped panel
- `apps/dsa-web/src/components/report/RefreshPriceButton.tsx` — wraps `stocksApi.getQuote`
- `apps/dsa-web/src/components/report/PriceMapCard.tsx` — horizontal price-line with level markers
- `apps/dsa-web/src/api/stocks.ts` — `stocksApi.getQuote` typed wrapper

## 为什么这么改
See [evidence-grounded decision pipeline design Section C lines 485–563](docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md) (Phase 4 row in Section E).

**Spec deviation:** reuses existing `GET /api/v1/stocks/{code}/quote` instead of creating a new `/quote/{code}` endpoint, per AGENTS.md "优先复用现有模块". See plan §"Scope deviation from spec" for the trade-off.

## 验证情况
- `cd apps/dsa-web && npm run test` — all green, +36 new tests
- `cd apps/dsa-web && npm run lint` — clean
- `cd apps/dsa-web && npm run build` — clean (`tsc -b` + vite build)
- `./scripts/ci_gate.sh` — no backend changes touched; gate stays green

## 未验证项
- No browser smoke — components are not mounted anywhere, so manual smoke is meaningless in this PR. Phase 5 will smoke them when wired into the report.
- Desktop app (`apps/dsa-desktop/`) not touched — Phase 4 is web-only per spec.

## 风险点
- Low. All new code; existing components untouched. New types are additive.
- One small surface: `EvidenceExpansion` and `EvidenceRef` will be subject to design polish in Phase 5 before they're shown to users.

## 回滚方式
`git revert <merge-commit>` is safe — no migrations, no runtime feature flag, no consumer wiring.
```

- [ ] **Step 3: Self-review checklist before requesting review**

- [ ] Test file count matches plan: 5 new test files under `apps/dsa-web/src/{hooks,components/report,api}/__tests__/`
- [ ] Every new component returns `null` for empty / invalid inputs
- [ ] No new dependency in `apps/dsa-web/package.json` other than `@testing-library/user-event` (which may have already been present)
- [ ] No edits under `src/notification.py`, `src/services/history_service.py`, `src/analysis/`, or `api/v1/endpoints/`
- [ ] Branch is rebased on `main` (no merge conflicts pending)

---

## Self-Review (executed by plan author, 2026-05-24)

**Spec coverage:**
- Section C 组件清单 rows for `PriceMapCard`, `EvidenceExpansion`, `EvidenceRef`, `useFactBundle`, `RefreshPriceButton` → Tasks 2, 3, 4, 6, 7 ✓
- Section C `ActionPlanTable.tsx` 重写 / `StrategyHeroCard.tsx` 新建 / `PositionFlowTimeline.tsx` 新建 / `StrategySelector.tsx` 删除 / `StrategyThesis.tsx` 删除 / `PositionOutcomeSummary.tsx` 删除 / `ReportSummary.tsx` 改造 — **deferred to Phase 5** per Section E phase split (this is the "前端集成" phase). Not a gap; out of scope by design.
- Section C "API 新增 endpoint" → handled by scope deviation note + reuse of existing `/stocks/{code}/quote`. Documented.
- Section D 前端测试 table — every row that involves a Phase-4 component has a corresponding test file in Tasks 2-7. `ActionPlanTable.test.tsx` and `StrategyHeroCard.test.tsx` and `PositionFlowTimeline.test.tsx` are correctly deferred to Phase 5.

**Placeholder scan:** no "TBD", no "add appropriate error handling", no "implement later". One conditional note remains: Task 6 Step 2 ("if `@testing-library/user-event` is MISSING, install it") — this is a genuine conditional based on actual current state, not a placeholder.

**Type consistency:**
- `FactRecord.id` (snake_case property name on the wire) is consistent across all tasks ✓
- `useFactBundle` returns `{ getFact, byType, byPrefix }` — all three are referenced consistently in `EvidenceExpansion` ✓
- `stocksApi.getQuote` returns `QuoteResponse { stockCode, currentPrice, asOf, changePercent }` — `RefreshPriceButton` calls `q.currentPrice` and `q.asOf` ✓
- `PriceMapLevel` shape (`factId`, `price`, `label`, `color`, `role`) — matches spec Section C lines 519-530 ✓
- `PriceMapCardProps.onRefresh` signature `() => Promise<{price, asOf}>` — matches `RefreshPriceButton.onQuote` callback shape ✓

No gaps found, no inconsistencies. Plan is ready for execution after PR #10 and #11 land on `main`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-phase-4-frontend-base.md`.

**Execution gate:** Do NOT start Task 1 until both PR #10 and PR #11 are merged to `main`. Then:

```bash
git checkout main
git pull
git checkout -b feat/phase-4-frontend-base
```

**Recommended execution mode:** Inline via `superpowers:executing-plans` (no SDD dispatch — task code blocks are within size limits, but per [[feedback-subagent-prompt-size-limit]] inline is safer for plans that include full component source).
