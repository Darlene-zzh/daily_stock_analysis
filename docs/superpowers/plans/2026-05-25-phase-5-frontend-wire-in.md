# Phase 5 Frontend Wire-In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount the Phase 4 atomic evidence components (`PriceMapCard`, `EvidenceRef`, `EvidenceExpansion`, `RefreshPriceButton`) into the actual stock report page, build the two missing composite components (`StrategyHeroCard`, `PositionFlowTimeline`), and retire the three superseded components (`StrategySelector`, `StrategyThesis`, `PositionOutcomeSummary`) so end users see the evidence-grounded UI per spec Section C.

**Architecture:** The Phase 4 components were authored against the `FactBundle` types in `apps/dsa-web/src/types/analysis.ts:529-591`, which mirror the backend's snake_case wire shape (`display_value`, `basis_fact_id`, `applicable_strategies`, `distance_pct_from_current`, etc.). The blocking issue is that the API layer's `toCamelCase` helper at `apps/dsa-web/src/api/utils.ts:12` runs `camelcase-keys` with `{ deep: true }`, which silently mangles the bundle on the way in — so `useFactBundle` and every Phase 4 component receive a shape they cannot read. Task 1 closes that hole by adding `stopPaths` to preserve `dashboard.fact_bundle` verbatim. Tasks 2-4 thread the typed bundle into `ReportSummary` and mount `PriceMapCard`. Tasks 5-8 build the remaining composite components and rewrite `ActionPlanTable`. Task 9 deletes the three superseded files. Tasks 10-11 verify nothing else broke and capture a screenshot for the PR.

**Tech Stack:** React 18 + TypeScript + Vite + Vitest + `@testing-library/react` + Tailwind. `camelcase-keys` v10 (`stopPaths` option). All visual work uses existing `clsx` + Tailwind utility classes — no new dependencies.

---

### Task 1: Preserve `dashboard.fact_bundle` snake_case at the camelcase boundary

**Context:** `toCamelCase` is called once on the full response (path `report.dashboard.fact_bundle`) and once on the inner report (path `dashboard.fact_bundle`). Both call sites must preserve the bundle. We bake a default `stopPaths` list into the helper so callers cannot forget; current callers in `analysis.ts`/`decisionJournal.ts`/`backtest.ts`/`portfolio.ts` inherit the protection without source edits.

**Files:**
- Modify: `apps/dsa-web/src/api/utils.ts`
- Create: `apps/dsa-web/src/api/__tests__/utils.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/api/__tests__/utils.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { toCamelCase } from '../utils';

describe('toCamelCase', () => {
  it('camelizes ordinary snake_case keys deeply', () => {
    const out = toCamelCase<{ outerKey: { innerKey: number } }>({
      outer_key: { inner_key: 1 },
    });
    expect(out).toEqual({ outerKey: { innerKey: 1 } });
  });

  it('preserves dashboard.fact_bundle untouched (top-level path)', () => {
    const raw = {
      dashboard: {
        core_conclusion: { recommended_strategy: 'swing_trade' },
        fact_bundle: {
          as_of: '2026-05-25T00:00:00Z',
          market: 'us',
          stock_code: 'NVDA',
          facts: [
            {
              id: 'technical.resistance',
              type: 'technical',
              label: '阻力位',
              value: 226.13,
              display_value: '$226.13',
              basis_fact_id: 'technical.resistance',
            },
          ],
          candidates: [
            {
              id: 'candidate.exit.1',
              direction: 'take_profit',
              basis_fact_id: 'technical.resistance',
              basis_rule: 'resistance_touch',
              applicable_strategies: ['swing_trade'],
              distance_pct_from_current: 1.19,
            },
          ],
        },
      },
    };
    const out = toCamelCase<typeof raw>(raw);
    expect(out.dashboard.core_conclusion).toBeUndefined(); // siblings camelized
    expect((out as any).dashboard.coreConclusion.recommendedStrategy).toBe('swing_trade');
    // factBundle is the camelized outer key — but its body is preserved
    expect((out as any).dashboard.factBundle.as_of).toBe('2026-05-25T00:00:00Z');
    expect((out as any).dashboard.factBundle.stock_code).toBe('NVDA');
    expect((out as any).dashboard.factBundle.facts[0].display_value).toBe('$226.13');
    expect((out as any).dashboard.factBundle.facts[0].basis_fact_id).toBe('technical.resistance');
    expect((out as any).dashboard.factBundle.candidates[0].basis_rule).toBe('resistance_touch');
    expect((out as any).dashboard.factBundle.candidates[0].applicable_strategies).toEqual(['swing_trade']);
    expect((out as any).dashboard.factBundle.candidates[0].distance_pct_from_current).toBe(1.19);
  });

  it('preserves report.dashboard.fact_bundle untouched (nested under report)', () => {
    const raw = {
      report: {
        dashboard: {
          fact_bundle: {
            stock_code: 'AAPL',
            facts: [{ id: 'x', type: 'technical', label: 'x', value: 1, display_value: '1' }],
            candidates: [],
          },
        },
      },
    };
    const out = toCamelCase<typeof raw>(raw);
    expect((out as any).report.dashboard.factBundle.stock_code).toBe('AAPL');
    expect((out as any).report.dashboard.factBundle.facts[0].display_value).toBe('1');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/api/__tests__/utils.test.ts`
Expected: 2 of 3 tests FAIL (the two preservation tests). The "camelizes ordinary" test passes, the two `fact_bundle` tests fail because keys like `display_value` get camelized to `displayValue`.

- [ ] **Step 3: Update `toCamelCase` to use default `stopPaths`**

Replace the entire body of `apps/dsa-web/src/api/utils.ts` with:

```typescript
import camelcaseKeys from 'camelcase-keys';

/**
 * Paths kept in snake_case across every API response. Mirrors the contract in
 * `apps/dsa-web/src/types/analysis.ts:529-591` — the FactBundle wire body is
 * authored snake_case (basis_fact_id, display_value, applicable_strategies,
 * distance_pct_from_current, ...) and must remain so for Phase 4 components
 * (EvidenceRef, EvidenceExpansion, PriceMapCard, useFactBundle) to read it.
 *
 * The outer key `fact_bundle` itself still gets camelcased to `factBundle` —
 * `stopPaths` halts traversal AFTER the path resolves, not at the path key.
 */
const DEFAULT_STOP_PATHS: readonly string[] = [
    'dashboard.fact_bundle',
    'report.dashboard.fact_bundle',
];

/**
 * 将 snake_case 对象键转换为 camelCase
 * @param data API 响应数据 (snake_case)
 * @returns 转换后的 camelCase 对象
 */
export function toCamelCase<T>(data: unknown): T {
    if (data === null || data === undefined) {
        return data as T;
    }
    return camelcaseKeys(data as Record<string, unknown>, {
        deep: true,
        stopPaths: DEFAULT_STOP_PATHS,
    }) as T;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/api/__tests__/utils.test.ts`
Expected: 3 of 3 PASS.

- [ ] **Step 5: Re-run the broader API/hook test surface to confirm no regression**

Run: `cd apps/dsa-web && npx vitest run src/api src/hooks/__tests__/useFactBundle.test.tsx`
Expected: all green. The pre-existing `stocks.test.ts` / `systemConfig.test.ts` / `useFactBundle.test.tsx` should be unchanged.

- [ ] **Step 6: Commit**

```bash
git checkout -b feat/phase-5-frontend-wire-in
git add apps/dsa-web/src/api/utils.ts apps/dsa-web/src/api/__tests__/utils.test.ts
git commit -m "fix(api): preserve dashboard.fact_bundle snake_case across toCamelCase boundary"
```

---

### Task 2: Type `DashboardSection.factBundle` + extend `StrategyChoice` + structured `strategyThesis`

**Context:** Now that the bundle survives the boundary, declare it on the typed `DashboardSection` so consumers don't need `as any`. Per spec Section B, also extend `StrategyChoice` with `supportingEvidenceRefs` / `contradictingEvidenceRefs`, and allow `strategyThesis` to be the structured object `{ text, evidence_refs, provenance }` OR the legacy string. Snake_case for the structured thesis body (it ships inside the same bundle-preserving pipe? — no, it ships under `coreConclusion`, which IS camelcased; so the structured form keeps camelCase keys). All new fields are optional → backwards compatible with old reports.

**Files:**
- Modify: `apps/dsa-web/src/types/analysis.ts:162-239`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/types/__tests__/analysis.types.test.ts`:

```typescript
import { describe, it, expectTypeOf } from 'vitest';
import type {
  DashboardSection,
  FactBundle,
  StrategyChoice,
  CoreConclusion,
  StrategyThesisStructured,
} from '../analysis';

describe('analysis types — Phase 5 extensions', () => {
  it('DashboardSection exposes factBundle as a typed FactBundle | undefined', () => {
    expectTypeOf<DashboardSection['factBundle']>().toEqualTypeOf<FactBundle | undefined>();
  });

  it('StrategyChoice has optional evidence ref arrays', () => {
    expectTypeOf<StrategyChoice['supportingEvidenceRefs']>().toEqualTypeOf<string[] | undefined>();
    expectTypeOf<StrategyChoice['contradictingEvidenceRefs']>().toEqualTypeOf<string[] | undefined>();
  });

  it('CoreConclusion.strategyThesis accepts string OR structured object', () => {
    type T = NonNullable<CoreConclusion['strategyThesis']>;
    const asString: T = 'plain thesis text';
    const asStruct: T = {
      text: 'structured',
      evidenceRefs: ['technical.ma20'],
      provenance: 'llm',
    } satisfies StrategyThesisStructured;
    void asString;
    void asStruct;
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/types/__tests__/analysis.types.test.ts`
Expected: type errors / missing-export failures for `factBundle`, `supportingEvidenceRefs`, `contradictingEvidenceRefs`, `StrategyThesisStructured`.

- [ ] **Step 3: Extend the types**

In `apps/dsa-web/src/types/analysis.ts`, edit the `StrategyChoice` interface (lines 163-172) by appending two optional fields BEFORE the closing brace:

```typescript
export interface StrategyChoice {
  id: 'long_term_hold' | 'swing_trade' | 'stepped_profit_taking' | 'wait_and_see' | string;
  labelZh?: string;
  emoji?: string;
  applicable?: boolean;
  fitCondition?: string;
  keyParams?: string;
  timeHorizon?: string;
  inapplicableReason?: string;
  // Phase 5 evidence-grounding fields (optional, additive).
  supportingEvidenceRefs?: string[];
  contradictingEvidenceRefs?: string[];
}
```

Add the structured thesis type AFTER `StrategyChoice` (still around line 173):

```typescript
/** Structured strategy thesis emitted by the evidence-grounded pipeline. */
export interface StrategyThesisStructured {
  text: string;
  evidenceRefs: string[];
  provenance: 'llm' | 'synthesized';
}
```

In the `CoreConclusion` interface (line 220-230), change `strategyThesis?: string;` to:

```typescript
  strategyThesis?: string | StrategyThesisStructured;
```

In the `DashboardSection` interface (line 232-239), append the `factBundle` field (and remove the trailing comma if needed):

```typescript
export interface DashboardSection {
  coreConclusion?: CoreConclusion;
  dataPerspective?: Record<string, unknown>;
  battlePlan?: Record<string, unknown>;
  intelligence?: Record<string, unknown> & {
    sentimentDimensions?: SentimentDimensions;
  };
  /** Phase 1+5 — evidence-grounded fact bundle. Snake_case body preserved by
   *  `apps/dsa-web/src/api/utils.ts` `DEFAULT_STOP_PATHS`. */
  factBundle?: FactBundle;
}
```

- [ ] **Step 4: Run test to verify it passes + type-check the project**

Run: `cd apps/dsa-web && npx vitest run src/types/__tests__/analysis.types.test.ts && npx tsc --noEmit`
Expected: types test PASS, full project type-check PASS (no other consumer regresses — `StrategyThesis.tsx` will still compile because it accesses `thesis` as a string prop and we haven't changed its prop type yet; it'll be deleted in Task 9 anyway).

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/types/analysis.ts apps/dsa-web/src/types/__tests__/analysis.types.test.ts
git commit -m "feat(types): expose factBundle + structured strategyThesis + strategy evidence refs"
```

---

### Task 3: New util `buildPriceMapLevels` — derive `PriceMapLevel[]` from `FactBundle`

**Context:** `PriceMapCard` expects an array of `PriceMapLevel { factId, price, label, color, role }`. We harvest these from the bundle: every `technical.*` price-like fact (`current_price`, `ma5/10/20`, `support`, `resistance`) plus the primary-tier `candidate.*` levels (stops/targets). A pure helper with a `null`-bundle fallback to `battlePlan.sniperPoints` (legacy reports) keeps the component dumb.

**Files:**
- Create: `apps/dsa-web/src/utils/priceMapLevels.ts`
- Create: `apps/dsa-web/src/utils/__tests__/priceMapLevels.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/utils/__tests__/priceMapLevels.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { buildPriceMapLevels } from '../priceMapLevels';
import type { FactBundle } from '../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.current_price', type: 'technical', label: '现价', value: 223.47, display_value: '$223.47' },
    { id: 'technical.ma10', type: 'technical', label: 'MA10', value: 222.02, display_value: '$222.02' },
    { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 213.40, display_value: '$213.40' },
    { id: 'technical.support', type: 'technical', label: '支撑位', value: 222.02, display_value: '$222.02' },
    { id: 'technical.resistance', type: 'technical', label: '阻力位', value: 226.13, display_value: '$226.13' },
    { id: 'technical.rsi_12', type: 'technical', label: 'RSI(12)', value: 71.1, display_value: '71.1' },
    { id: 'committee.pm_verdict', type: 'committee', label: 'PM 裁决', value: 'hold', display_value: 'hold' },
  ],
  candidates: [
    { id: 'candidate.exit.1', type: 'candidate', label: '阻力位止盈', value: 226.13, display_value: '$226.13',
      direction: 'take_profit', price: 226.13, basis_fact_id: 'technical.resistance', basis_rule: 'resistance_touch',
      applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: 1.19 },
    { id: 'candidate.stop.1', type: 'candidate', label: 'MA20 止损', value: 213.39, display_value: '$213.39',
      direction: 'stop_loss', price: 213.39, basis_fact_id: 'technical.ma20', basis_rule: 'ma20_breakdown',
      applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -4.51 },
    { id: 'candidate.exit.2', type: 'candidate', label: '心理位', value: 230, display_value: '$230',
      direction: 'take_profit', price: 230, basis_fact_id: 'technical.resistance', basis_rule: 'psychological_round',
      applicable_strategies: ['swing_trade'], tier: 'secondary', distance_pct_from_current: 2.92 },
    { id: 'candidate.anchor.1', type: 'candidate', label: 'cost+5%', value: 250, display_value: '$250',
      direction: 'take_profit', price: 250, basis_fact_id: 'portfolio.avg_cost', basis_rule: 'cost_plus_5pct',
      applicable_strategies: ['stepped_profit_taking'], tier: 'discipline_anchor', distance_pct_from_current: 11.87 },
  ],
};

describe('buildPriceMapLevels', () => {
  it('emits MA10/MA20/support/resistance facts with role+color', () => {
    const out = buildPriceMapLevels(bundle);
    const ma20 = out.find((l) => l.factId === 'technical.ma20');
    expect(ma20).toMatchObject({ price: 213.4, label: 'MA20', role: 'ma', color: 'blue' });
    const resistance = out.find((l) => l.factId === 'technical.resistance');
    expect(resistance).toMatchObject({ role: 'resistance', color: 'orange' });
    const support = out.find((l) => l.factId === 'technical.support');
    expect(support).toMatchObject({ role: 'support', color: 'green' });
  });

  it('emits primary-tier candidates with stop/target roles', () => {
    const out = buildPriceMapLevels(bundle);
    const stop = out.find((l) => l.factId === 'candidate.stop.1');
    expect(stop).toMatchObject({ role: 'stop', color: 'red', price: 213.39 });
    const target = out.find((l) => l.factId === 'candidate.exit.1');
    expect(target).toMatchObject({ role: 'target', color: 'green', price: 226.13 });
  });

  it('drops secondary and discipline_anchor candidates from the price map', () => {
    const out = buildPriceMapLevels(bundle);
    expect(out.find((l) => l.factId === 'candidate.exit.2')).toBeUndefined();
    expect(out.find((l) => l.factId === 'candidate.anchor.1')).toBeUndefined();
  });

  it('skips non-price technical facts (RSI, current_price) and non-technical types', () => {
    const out = buildPriceMapLevels(bundle);
    expect(out.find((l) => l.factId === 'technical.rsi_12')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.current_price')).toBeUndefined();
    expect(out.find((l) => l.factId === 'committee.pm_verdict')).toBeUndefined();
  });

  it('returns [] for a null bundle', () => {
    expect(buildPriceMapLevels(null)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/utils/__tests__/priceMapLevels.test.ts`
Expected: FAIL with "Cannot find module '../priceMapLevels'".

- [ ] **Step 3: Implement `buildPriceMapLevels`**

Create `apps/dsa-web/src/utils/priceMapLevels.ts`:

```typescript
import type { FactBundle } from '../types/analysis';
import type { PriceMapLevel } from '../components/report/PriceMapCard';

const TECHNICAL_LEVEL_FACTS: Record<
  string,
  { role: PriceMapLevel['role']; color: PriceMapLevel['color']; label: string }
> = {
  'technical.ma5':        { role: 'ma',         color: 'blue',   label: 'MA5' },
  'technical.ma10':       { role: 'ma',         color: 'blue',   label: 'MA10' },
  'technical.ma20':       { role: 'ma',         color: 'blue',   label: 'MA20' },
  'technical.support':    { role: 'support',    color: 'green',  label: '支撑' },
  'technical.resistance': { role: 'resistance', color: 'orange', label: '阻力' },
};

/**
 * Build the `levels[]` prop for `PriceMapCard` from a FactBundle.
 *
 * Sources:
 *  - `technical.{ma5,ma10,ma20,support,resistance}` facts → MA / support / resistance markers
 *  - `candidate.*` items with `tier === 'primary'` → stop / target markers
 *
 * Skips: current_price, RSI, non-technical facts, and secondary / discipline_anchor candidates
 * (they bloat the axis and the C-spec called for restraint).
 */
export function buildPriceMapLevels(bundle: FactBundle | null | undefined): PriceMapLevel[] {
  if (!bundle) return [];

  const out: PriceMapLevel[] = [];

  for (const fact of bundle.facts) {
    const cfg = TECHNICAL_LEVEL_FACTS[fact.id];
    if (!cfg) continue;
    const price = typeof fact.value === 'number' ? fact.value : Number(fact.value);
    if (!Number.isFinite(price) || price <= 0) continue;
    out.push({ factId: fact.id, price, label: cfg.label, color: cfg.color, role: cfg.role });
  }

  for (const cand of bundle.candidates) {
    if (cand.tier !== 'primary') continue;
    if (cand.direction === 'stop_loss' || cand.direction === 'stop') {
      out.push({ factId: cand.id, price: cand.price, label: cand.label, color: 'red', role: 'stop' });
    } else if (cand.direction === 'take_profit' || cand.direction === 'exit') {
      out.push({ factId: cand.id, price: cand.price, label: cand.label, color: 'green', role: 'target' });
    }
  }

  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/utils/__tests__/priceMapLevels.test.ts`
Expected: 5 of 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/utils/priceMapLevels.ts apps/dsa-web/src/utils/__tests__/priceMapLevels.test.ts
git commit -m "feat(utils): buildPriceMapLevels — derive PriceMapCard levels from FactBundle"
```

---

### Task 4: Mount `PriceMapCard` at the top of `ReportSummary`

**Context:** Surface the price map as the first section after the cache banner (above `ReportOverview`). It only renders when `factBundle` is present and `technical.current_price` resolves to a positive number. Legacy reports without a bundle see no change.

**Files:**
- Modify: `apps/dsa-web/src/components/report/ReportSummary.tsx` (add import + render block)
- Create: `apps/dsa-web/src/components/report/__tests__/ReportSummary.priceMap.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/ReportSummary.priceMap.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReportSummary } from '../ReportSummary';
import type { AnalysisReport, FactBundle } from '../../../types/analysis';

// Stub the children components that pull in heavy deps (charts, contexts) so
// the test focuses on PriceMapCard wiring.
vi.mock('../../committee/CommitteeMinutesPanel', () => ({ CommitteeMinutesPanel: () => null }));
vi.mock('../../decisionTracking/DecisionTrackingTab', () => ({ DecisionTrackingTab: () => null }));
vi.mock('../../quant/QuantContextPanel', () => ({ QuantContextPanel: () => null }));
vi.mock('../../risk/StructuredRiskCallout', () => ({ StructuredRiskCallout: () => null }));
vi.mock('../ReportNews', () => ({ ReportNews: () => null }));
vi.mock('../ReportOverview', () => ({ ReportOverview: () => <div data-testid="overview" /> }));
vi.mock('../ReportDetails', () => ({ ReportDetails: () => null }));
vi.mock('../ReportStrategy', () => ({ ReportStrategy: () => null }));

const factBundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.current_price', type: 'technical', label: '现价', value: 223.47, display_value: '$223.47' },
    { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 213.40, display_value: '$213.40' },
    { id: 'technical.resistance', type: 'technical', label: '阻力位', value: 226.13, display_value: '$226.13' },
  ],
  candidates: [],
};

function buildReport(opts: { withBundle: boolean }): AnalysisReport {
  return {
    meta: {
      id: 'rec-1',
      stockCode: 'NVDA',
      stockName: 'NVIDIA',
      market: 'us',
      generatedAt: '2026-05-25T00:00:00Z',
    } as unknown as AnalysisReport['meta'],
    summary: {} as AnalysisReport['summary'],
    dashboard: opts.withBundle ? { factBundle } : undefined,
  };
}

describe('ReportSummary + PriceMapCard wire-in', () => {
  it('mounts PriceMapCard when a factBundle with current_price is present', () => {
    render(<ReportSummary data={buildReport({ withBundle: true })} />);
    expect(screen.getByTestId('overview')).toBeInTheDocument();
    expect(document.querySelector('[data-component="price-map-card"]')).not.toBeNull();
  });

  it('does NOT mount PriceMapCard when factBundle is absent (legacy report)', () => {
    render(<ReportSummary data={buildReport({ withBundle: false })} />);
    expect(document.querySelector('[data-component="price-map-card"]')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ReportSummary.priceMap.test.tsx`
Expected: first test FAILs (PriceMapCard not rendered), second PASSes.

- [ ] **Step 3: Wire PriceMapCard into ReportSummary**

In `apps/dsa-web/src/components/report/ReportSummary.tsx`, add the imports near the existing component imports (after line 12):

```typescript
import { PriceMapCard } from './PriceMapCard';
import { buildPriceMapLevels } from '../../utils/priceMapLevels';
```

Inside the component body, AFTER the `cacheAgeLabel` line (line 67) and BEFORE the `return` (line 69), add:

```typescript
  const factBundle = report.dashboard?.factBundle;
  const currentPriceFact = factBundle?.facts.find((f) => f.id === 'technical.current_price');
  const currentPrice = typeof currentPriceFact?.value === 'number' ? currentPriceFact.value : null;
  const priceMapLevels = buildPriceMapLevels(factBundle);
  const showPriceMap = factBundle != null && currentPrice != null && currentPrice > 0 && priceMapLevels.length > 0;
```

Inside the JSX, INSERT a new block AFTER the `isCached` banner (line 93) and BEFORE the `{/* 概览区（首屏） */}` comment (line 94):

```tsx
      {showPriceMap && currentPrice != null && (
        <PriceMapCard
          stockCode={meta.stockCode}
          currentPrice={currentPrice}
          currentPriceAsOf={currentPriceFact?.as_of ?? factBundle.as_of}
          levels={priceMapLevels}
        />
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ReportSummary.priceMap.test.tsx`
Expected: 2 of 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/ReportSummary.tsx apps/dsa-web/src/components/report/__tests__/ReportSummary.priceMap.test.tsx
git commit -m "feat(report): mount PriceMapCard at top of ReportSummary when factBundle present"
```

---

### Task 5: Extend `ActionPlanTable` — render `EvidenceExpansion` + `provenance` + `narrative` + `tier`

**Context:** Existing rows still render their cost-based fallback fields (`technicalBasis`, `fundamentalBasis`, `quantSignal`, `invalidationRule`). Phase 5 adds three layers ON TOP, all guarded by field presence so legacy reports stay clean:
1. Provenance badge (🤖 代码兜底) when `provenance === 'synthesized'`
2. Tier pill (📌 纪律锚) when `tier === 'discipline_anchor'`
3. `narrative` paragraph + `EvidenceExpansion` panel when `evidenceRefs?.length > 0`, both inside the expandable region

The component receives the `factBundle` as a new optional prop so the expansion has a lookup source.

**Files:**
- Modify: `apps/dsa-web/src/components/report/ActionPlanTable.tsx`
- Modify: `apps/dsa-web/src/components/report/ReportSummary.tsx` (pass `factBundle` prop)
- Create: `apps/dsa-web/src/components/report/__tests__/ActionPlanTable.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/ActionPlanTable.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ActionPlanTable } from '../ActionPlanTable';
import type { ActionPlanItem, FactBundle } from '../../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.resistance', type: 'technical', label: '阻力位', value: 226.13, display_value: '$226.13' },
    { id: 'committee.pm_verdict', type: 'committee', label: 'PM 裁决', value: 'hold', display_value: 'hold (5.8/10)' },
  ],
  candidates: [
    { id: 'candidate.exit.1', type: 'candidate', label: '阻力位止盈', value: 226.13, display_value: '$226.13',
      direction: 'take_profit', price: 226.13, basis_fact_id: 'technical.resistance', basis_rule: 'resistance_touch',
      applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: 1.19 },
  ],
};

function baseItem(overrides: Partial<ActionPlanItem> = {}): ActionPlanItem {
  return {
    triggerPrice: 226.13,
    triggerCondition: '阻力位触及',
    direction: 'take_profit',
    shares: 0.2279,
    pctOfPosition: 30,
    pctOfEquity: 3.5,
    technicalBasis: '',
    fundamentalBasis: '',
    quantSignal: '',
    invalidationRule: '放量站稳 $230 上方',
    priority: 1,
    ...overrides,
  };
}

describe('ActionPlanTable — Phase 5 wire-in', () => {
  it('renders nothing when items is empty', () => {
    const { container } = render(<ActionPlanTable items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders header + a row with trigger price for the legacy shape', () => {
    render(<ActionPlanTable items={[baseItem()]} />);
    expect(screen.getByText('📋 持仓操作计划')).toBeInTheDocument();
    expect(screen.getByText('$226.13')).toBeInTheDocument();
  });

  it('shows 🤖 代码兜底 badge when provenance is synthesized', () => {
    render(<ActionPlanTable items={[baseItem({ provenance: 'synthesized' })]} />);
    expect(screen.getByText(/代码兜底/)).toBeInTheDocument();
  });

  it('shows 📌 纪律锚 pill when tier is discipline_anchor', () => {
    render(<ActionPlanTable items={[baseItem({ tier: 'discipline_anchor' })]} />);
    expect(screen.getByText(/纪律锚/)).toBeInTheDocument();
  });

  it('renders narrative + EvidenceExpansion under the expandable region when evidenceRefs present', () => {
    render(
      <ActionPlanTable
        bundle={bundle}
        items={[
          baseItem({
            candidateId: 'candidate.exit.1',
            evidenceRefs: ['technical.resistance', 'committee.pm_verdict'],
            narrative: '阻力位触及减仓，PM 中性。',
            tier: 'primary',
            provenance: 'llm',
          }),
        ]}
      />,
    );
    // Narrative is hidden behind the disclosure
    expect(screen.queryByText(/阻力位触及减仓/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/查看分析依据/));
    expect(screen.getByText(/阻力位触及减仓/)).toBeInTheDocument();
    // EvidenceExpansion renders the two group headers
    expect(screen.getByText(/技术（1）/)).toBeInTheDocument();
    expect(screen.getByText(/委员会（1）/)).toBeInTheDocument();
  });

  it('does NOT render EvidenceExpansion when bundle is missing even if refs are present', () => {
    render(
      <ActionPlanTable
        items={[baseItem({ evidenceRefs: ['technical.resistance'], narrative: 'n' })]}
      />,
    );
    fireEvent.click(screen.getByText(/查看分析依据/));
    expect(screen.getByText('n')).toBeInTheDocument();
    expect(screen.queryByText(/技术（1）/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ActionPlanTable.test.tsx`
Expected: 4 of 6 fail (the four asserting new badges/narrative/expansion); the first two pass.

- [ ] **Step 3: Extend ActionPlanTable**

Replace the entire body of `apps/dsa-web/src/components/report/ActionPlanTable.tsx` with:

```typescript
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
  buy: { emoji: '⬆️', label: '买入/加仓', colorClass: 'text-emerald-400' },
  sell: { emoji: '⬇️', label: '减仓', colorClass: 'text-amber-400' },
  stop_loss: { emoji: '🛑', label: '止损清仓', colorClass: 'text-red-400' },
  take_profit: { emoji: '🎯', label: '止盈', colorClass: 'text-blue-400' },
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
    item.pctOfEquity != null ? `权益 ${item.pctOfEquity.toFixed(1)}%` : null,
  ]
    .filter(Boolean)
    .join(' / ');

  const hasEvidence = (item.evidenceRefs?.length ?? 0) > 0;
  const hasNarrative = Boolean(item.narrative && item.narrative.trim());
  const hasLegacyBasis = Boolean(
    item.technicalBasis || item.fundamentalBasis || item.quantSignal || item.invalidationRule,
  );
  const showExpandToggle = hasEvidence || hasNarrative || hasLegacyBasis;

  return (
    <div className="rounded-lg border border-subtle bg-surface/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {ordinal} {cfg.emoji}{' '}
            <span className={cfg.colorClass}>{cfg.label}</span>
          </span>
          <span className="text-xs text-muted-text">优先级 {item.priority}</span>
          {item.tier === 'discipline_anchor' && (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
              📌 纪律锚
            </span>
          )}
          {item.provenance === 'synthesized' && (
            <span className="rounded bg-slate-500/15 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
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
              {Number.isInteger(item.shares) ? item.shares : item.shares.toFixed(4)} 股
              {posStr ? ` (${posStr})` : ''}
            </span>
          )}
        </div>
      </div>

      <p className="mt-1 text-xs text-secondary-text">{item.triggerCondition}</p>

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
              evidenceRefs={item.evidenceRefs!}
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
```

In `apps/dsa-web/src/components/report/ReportSummary.tsx`, find the `<ActionPlanTable items=... />` call (around line 106) and add the `bundle` prop:

```tsx
            <ActionPlanTable
              items={report.dashboard.coreConclusion.actionPlanItems}
              bundle={factBundle}
            />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ActionPlanTable.test.tsx src/components/report/__tests__/ReportSummary.priceMap.test.tsx`
Expected: all PASS (6 in ActionPlanTable + 2 in ReportSummary priceMap).

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/ActionPlanTable.tsx apps/dsa-web/src/components/report/ReportSummary.tsx apps/dsa-web/src/components/report/__tests__/ActionPlanTable.test.tsx
git commit -m "feat(report): ActionPlanTable renders evidence, narrative, provenance, tier badges"
```

---

### Task 6: New `StrategyHeroCard` — replace `StrategyThesis` + `StrategySelector` with a unified hero + alternatives

**Context:** Per spec Section C, the "策略选择" + "AI 推荐策略" sections collapse into one card with three regions:
1. Hero: the recommended strategy (emoji + label + thesis text + citation pills for `evidenceRefs`)
2. Alternatives: the non-recommended applicable choices (compact grid, smaller font)
3. Inapplicable list at the bottom (one-line each, muted)

Citation pills come from `EvidenceRef` resolved via the bundle. `strategyThesis` can be a string (legacy) or a `StrategyThesisStructured` (new) — handle both.

**Files:**
- Create: `apps/dsa-web/src/components/report/StrategyHeroCard.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/StrategyHeroCard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/StrategyHeroCard.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StrategyHeroCard } from '../StrategyHeroCard';
import type { FactBundle, StrategyChoice } from '../../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 213.4, display_value: '$213.40' },
    { id: 'committee.pm_verdict', type: 'committee', label: 'PM 裁决', value: 'hold', display_value: 'hold (5.8/10)' },
  ],
  candidates: [],
};

const choices: StrategyChoice[] = [
  { id: 'swing_trade', labelZh: '短线波段', emoji: '⚡', applicable: true,
    fitCondition: 'RSI 超买，等回踩 MA10', timeHorizon: '1-2 周' },
  { id: 'stepped_profit_taking', labelZh: '阶梯式止盈', emoji: '🪜', applicable: true,
    fitCondition: '已有浮盈，分批了结' },
  { id: 'long_term_hold', labelZh: '长线持有', emoji: '🌳', applicable: false,
    inapplicableReason: '估值已脱离基本面' },
];

describe('StrategyHeroCard', () => {
  it('renders nothing when no choices and no thesis', () => {
    const { container } = render(<StrategyHeroCard choices={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('highlights the recommended strategy as the hero and renders its thesis text', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        thesis="RSI 71.1 超买，等回踩 MA10 再进。"
      />,
    );
    expect(screen.getByText(/AI 推荐策略：短线波段/)).toBeInTheDocument();
    expect(screen.getByText(/RSI 71.1 超买，等回踩 MA10 再进。/)).toBeInTheDocument();
  });

  it('renders citation pills for structured thesis evidenceRefs', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        bundle={bundle}
        thesis={{
          text: '配合 PM 中性观点。',
          evidenceRefs: ['technical.ma20', 'committee.pm_verdict'],
          provenance: 'llm',
        }}
      />,
    );
    expect(screen.getByText('MA20')).toBeInTheDocument();
    expect(screen.getByText('PM 裁决')).toBeInTheDocument();
  });

  it('shows alternatives below the hero with smaller styling', () => {
    render(<StrategyHeroCard choices={choices} recommendedId="swing_trade" />);
    expect(screen.getByText(/其他候选策略/)).toBeInTheDocument();
    expect(screen.getByText('🪜 阶梯式止盈')).toBeInTheDocument();
  });

  it('lists inapplicable strategies at the bottom with reasons', () => {
    render(<StrategyHeroCard choices={choices} recommendedId="swing_trade" />);
    expect(screen.getByText(/不适用/)).toBeInTheDocument();
    expect(screen.getByText(/估值已脱离基本面/)).toBeInTheDocument();
  });

  it('renders 🤖 provenance badge when structured thesis is synthesized', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        thesis={{ text: 't', evidenceRefs: [], provenance: 'synthesized' }}
      />,
    );
    expect(screen.getByText(/代码兜底/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/StrategyHeroCard.test.tsx`
Expected: FAIL with "Cannot find module '../StrategyHeroCard'".

- [ ] **Step 3: Implement StrategyHeroCard**

Create `apps/dsa-web/src/components/report/StrategyHeroCard.tsx`:

```typescript
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/StrategyHeroCard.test.tsx`
Expected: 6 of 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/StrategyHeroCard.tsx apps/dsa-web/src/components/report/__tests__/StrategyHeroCard.test.tsx
git commit -m "feat(report): StrategyHeroCard — hero + alternatives + citation pills + provenance"
```

---

### Task 7: New `PositionFlowTimeline` — replace `PositionOutcomeSummary` with timeline + summary

**Context:** Same data shape as `PositionOutcomeSummary` (`remainingSharesAfterAllTriggers`, `worstCase*`, `bestCase*`, `riskRewardRatio`) plus an optional `triggers: ActionPlanItem[]` so we can render the chronological flow above the summary card. The timeline is a vertical list of dot+label rows; the summary stays the 2×2 grid we already had.

**Files:**
- Create: `apps/dsa-web/src/components/report/PositionFlowTimeline.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/PositionFlowTimeline.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/PositionFlowTimeline.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PositionFlowTimeline } from '../PositionFlowTimeline';
import type { ActionPlanItem, PositionOutcomeSummary } from '../../../types/analysis';

const summary: PositionOutcomeSummary = {
  remainingSharesAfterAllTriggers: 0.5,
  worstCaseLossAmount: 12.34,
  worstCaseCurrency: 'GBP',
  bestCaseGainAmount: 45.67,
  riskRewardRatio: '1:3.7',
};

const triggers: ActionPlanItem[] = [
  { triggerPrice: 226.13, triggerCondition: '阻力位触及', direction: 'take_profit',
    shares: 0.2279, pctOfPosition: 30, pctOfEquity: 3.5,
    technicalBasis: '', fundamentalBasis: '', quantSignal: '', invalidationRule: '', priority: 1 },
  { triggerPrice: 213.40, triggerCondition: 'MA20 跌破', direction: 'stop_loss',
    shares: 0.7597, pctOfPosition: 100, pctOfEquity: 11.5,
    technicalBasis: '', fundamentalBasis: '', quantSignal: '', invalidationRule: '', priority: 2 },
];

describe('PositionFlowTimeline', () => {
  it('renders nothing when summary is empty and no triggers', () => {
    const { container } = render(
      <PositionFlowTimeline summary={{} as PositionOutcomeSummary} triggers={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the summary grid with worst/best amounts and R/R ratio', () => {
    render(<PositionFlowTimeline summary={summary} triggers={[]} />);
    expect(screen.getByText('📊 仓位流水汇总')).toBeInTheDocument();
    expect(screen.getByText('12.34 GBP')).toBeInTheDocument();
    expect(screen.getByText('+45.67 GBP')).toBeInTheDocument();
    expect(screen.getByText('1:3.7')).toBeInTheDocument();
    expect(screen.getByText('0.5 股')).toBeInTheDocument();
  });

  it('renders a row per trigger in priority order with direction emoji + price', () => {
    render(<PositionFlowTimeline summary={summary} triggers={triggers} />);
    const rows = screen.getAllByTestId('flow-trigger-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('🎯');
    expect(rows[0]).toHaveTextContent('$226.13');
    expect(rows[1]).toHaveTextContent('🛑');
    expect(rows[1]).toHaveTextContent('$213.40');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/PositionFlowTimeline.test.tsx`
Expected: FAIL with "Cannot find module '../PositionFlowTimeline'".

- [ ] **Step 3: Implement PositionFlowTimeline**

Create `apps/dsa-web/src/components/report/PositionFlowTimeline.tsx`:

```typescript
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
          <p className="font-mono text-red-400">
            {summary.worstCaseLossAmount != null
              ? `${summary.worstCaseLossAmount} ${ccy}`.trim()
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-muted-text">最好止盈</p>
          <p className="font-mono text-emerald-400">
            {summary.bestCaseGainAmount != null
              ? `+${summary.bestCaseGainAmount} ${ccy}`.trim()
              : '—'}
          </p>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/PositionFlowTimeline.test.tsx`
Expected: 3 of 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/PositionFlowTimeline.tsx apps/dsa-web/src/components/report/__tests__/PositionFlowTimeline.test.tsx
git commit -m "feat(report): PositionFlowTimeline — trigger timeline + summary grid"
```

---

### Task 8: Swap `ReportSummary` to use `StrategyHeroCard` + `PositionFlowTimeline`

**Context:** Now that the new composites exist + tested, swap them in. The old `StrategySelector`, `StrategyThesis`, `PositionOutcomeSummary` imports stay in `ReportSummary` for one more task so we can run a clean delete with a single index.ts update in Task 9.

**Files:**
- Modify: `apps/dsa-web/src/components/report/ReportSummary.tsx`
- Create: `apps/dsa-web/src/components/report/__tests__/ReportSummary.composites.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/dsa-web/src/components/report/__tests__/ReportSummary.composites.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReportSummary } from '../ReportSummary';
import type { AnalysisReport } from '../../../types/analysis';

vi.mock('../../committee/CommitteeMinutesPanel', () => ({ CommitteeMinutesPanel: () => null }));
vi.mock('../../decisionTracking/DecisionTrackingTab', () => ({ DecisionTrackingTab: () => null }));
vi.mock('../../quant/QuantContextPanel', () => ({ QuantContextPanel: () => null }));
vi.mock('../../risk/StructuredRiskCallout', () => ({ StructuredRiskCallout: () => null }));
vi.mock('../ReportNews', () => ({ ReportNews: () => null }));
vi.mock('../ReportOverview', () => ({ ReportOverview: () => <div /> }));
vi.mock('../ReportDetails', () => ({ ReportDetails: () => null }));
vi.mock('../ReportStrategy', () => ({ ReportStrategy: () => null }));

function buildReport(): AnalysisReport {
  return {
    meta: { id: 'r', stockCode: 'NVDA', stockName: 'NVIDIA', market: 'us', generatedAt: '' } as unknown as AnalysisReport['meta'],
    summary: {} as AnalysisReport['summary'],
    dashboard: {
      coreConclusion: {
        actionPlanItems: [],
        strategyChoices: [
          { id: 'swing_trade', labelZh: '短线波段', emoji: '⚡', applicable: true, fitCondition: 'fit' },
        ],
        recommendedStrategy: 'swing_trade',
        strategyThesis: 'thesis text',
        positionOutcomeSummary: { riskRewardRatio: '1:2', worstCaseLossAmount: 10, bestCaseGainAmount: 20, worstCaseCurrency: 'USD' },
      },
    },
  };
}

describe('ReportSummary — composite swap', () => {
  it('renders StrategyHeroCard instead of StrategySelector + StrategyThesis', () => {
    render(<ReportSummary data={buildReport()} />);
    expect(screen.getByText(/AI 推荐策略：⚡ 短线波段/)).toBeInTheDocument();
    expect(screen.getByText('thesis text')).toBeInTheDocument();
    // Old separate "📌 策略选择" header from StrategySelector should be gone
    expect(screen.queryByText('📌 策略选择')).not.toBeInTheDocument();
  });

  it('renders PositionFlowTimeline (with summary grid)', () => {
    render(<ReportSummary data={buildReport()} />);
    expect(screen.getByText('📊 仓位流水汇总')).toBeInTheDocument();
    expect(screen.getByText('1:2')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ReportSummary.composites.test.tsx`
Expected: FAIL — the first assertion fails because `📌 策略选择` (rendered by old `StrategySelector`) is still present.

- [ ] **Step 3: Replace the two render blocks in `ReportSummary.tsx`**

In `apps/dsa-web/src/components/report/ReportSummary.tsx`, replace the imports for the three soon-to-be-replaced components AND add the new ones. Around line 9-12, change:

```typescript
import { StrategySelector } from './StrategySelector';
import { StrategyThesis } from './StrategyThesis';
import { SentimentPanel } from './SentimentPanel';
import { PositionOutcomeSummary } from './PositionOutcomeSummary';
```

to:

```typescript
import { StrategyHeroCard } from './StrategyHeroCard';
import { SentimentPanel } from './SentimentPanel';
import { PositionFlowTimeline } from './PositionFlowTimeline';
```

Replace the "策略选择" block (the existing `{report.dashboard?.coreConclusion?.strategyChoices && ...}` block, roughly lines 110-125) with:

```tsx
      {/* 策略英雄卡（推荐 + 备选 + 不适用） */}
      {report.dashboard?.coreConclusion?.strategyChoices &&
        report.dashboard.coreConclusion.strategyChoices.length > 0 && (
          <StrategyHeroCard
            choices={report.dashboard.coreConclusion.strategyChoices}
            recommendedId={report.dashboard.coreConclusion.recommendedStrategy}
            thesis={report.dashboard.coreConclusion.strategyThesis}
            bundle={factBundle}
          />
        )}
```

Replace the existing PositionOutcomeSummary block (roughly lines 127-132) with:

```tsx
      {/* 仓位流水时间线 + 汇总 */}
      {report.dashboard?.coreConclusion?.positionOutcomeSummary && (
        <PositionFlowTimeline
          summary={report.dashboard.coreConclusion.positionOutcomeSummary}
          triggers={report.dashboard.coreConclusion.actionPlanItems}
        />
      )}
```

- [ ] **Step 4: Run tests to verify it passes**

Run: `cd apps/dsa-web && npx vitest run src/components/report/__tests__/ReportSummary.composites.test.tsx src/components/report/__tests__/ReportSummary.priceMap.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/dsa-web/src/components/report/ReportSummary.tsx apps/dsa-web/src/components/report/__tests__/ReportSummary.composites.test.tsx
git commit -m "feat(report): swap ReportSummary to StrategyHeroCard + PositionFlowTimeline"
```

---

### Task 9: Delete superseded components + clean up `index.ts`

**Context:** `StrategySelector.tsx`, `StrategyThesis.tsx`, `PositionOutcomeSummary.tsx` are now orphans (only used by tests that we'll also remove). `index.ts` re-exports must drop them and add the new composites.

**Files:**
- Delete: `apps/dsa-web/src/components/report/StrategySelector.tsx`
- Delete: `apps/dsa-web/src/components/report/StrategyThesis.tsx`
- Delete: `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx`
- Modify: `apps/dsa-web/src/components/report/index.ts`

- [ ] **Step 1: Sanity-check there are no other consumers**

Run from repo root:

```bash
grep -rn "from.*StrategySelector\|from.*StrategyThesis\|from.*PositionOutcomeSummary" apps/dsa-web/src
```

Expected: zero matches in `apps/dsa-web/src` after `ReportSummary.tsx` swap from Task 8. If anything else references them, fix that consumer FIRST (do not delete blind).

- [ ] **Step 2: Delete the three files**

```bash
rm apps/dsa-web/src/components/report/StrategySelector.tsx
rm apps/dsa-web/src/components/report/StrategyThesis.tsx
rm apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx
```

- [ ] **Step 3: Update `index.ts`**

Replace the contents of `apps/dsa-web/src/components/report/index.ts` with:

```typescript
export * from './ReportSummary';
export * from './ReportOverview';
export * from './ReportStrategy';
export * from './ReportNews';
export * from './ReportDetails';
export * from './ReportMarkdown';
export { ActionPlanTable } from './ActionPlanTable';
export { StrategyHeroCard } from './StrategyHeroCard';
export { SentimentPanel } from './SentimentPanel';
export { PositionFlowTimeline } from './PositionFlowTimeline';
export { EvidenceRef } from './EvidenceRef';
export { EvidenceExpansion } from './EvidenceExpansion';
export { PriceMapCard } from './PriceMapCard';
export { RefreshPriceButton } from './RefreshPriceButton';
```

- [ ] **Step 4: Confirm type-check still passes**

Run: `cd apps/dsa-web && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add -A apps/dsa-web/src/components/report/
git commit -m "chore(report): remove superseded StrategySelector/StrategyThesis/PositionOutcomeSummary"
```

---

### Task 10: Full lint + build + targeted test sweep

**Context:** The plan only touches `src/api/utils.ts`, `src/types/analysis.ts`, `src/utils/priceMapLevels.ts`, and `src/components/report/*`. Per the handoff note, `apps/dsa-web` has 38-47 pre-existing baseline flakes unrelated to this work — we run lint + build (hard requirements) + the report/api/util/hook tests we touched (soft requirement). Any failure outside the changed surface is logged in the PR description as pre-existing, not blocking.

**Files:** (none modified)

- [ ] **Step 1: Lint**

Run: `cd apps/dsa-web && npm run lint`
Expected: PASS, or only the documented baseline warnings (no new errors introduced by Phase 5).

- [ ] **Step 2: Type-check + build**

Run: `cd apps/dsa-web && npm run build`
Expected: PASS, `dist/` produced.

- [ ] **Step 3: Targeted test sweep on the changed surface**

Run:
```bash
cd apps/dsa-web && npx vitest run \
  src/api/__tests__/utils.test.ts \
  src/api/__tests__/stocks.test.ts \
  src/types/__tests__/analysis.types.test.ts \
  src/hooks/__tests__/useFactBundle.test.tsx \
  src/utils/__tests__/priceMapLevels.test.ts \
  src/components/report/__tests__/
```
Expected: all PASS. If `ReportDetails.test.tsx` / `ReportNews.test.tsx` / `ReportMarkdown.test.tsx` / `ReportOverview.test.tsx` (pre-existing files we did not touch) regress, treat as a Phase 5 bug; if they were already red on `main`, log as pre-existing and continue.

- [ ] **Step 4: Backend smoke on the changed surface**

The bundle is only emitted by `src/core/pipeline.py:1789-1900` (Phase 1+2 code already on main). No backend changes in Phase 5 — but confirm the smoke still passes:

Run: `python3.11 -m pytest -m "not network" tests/test_pipeline.py tests/test_facts_builder.py -q`
Expected: PASS (no changes — sanity only).

- [ ] **Step 5: Commit any incidental cleanups produced by lint --fix**

If lint introduced auto-fixes:

```bash
git add -A apps/dsa-web/src
git commit -m "style(report): lint --fix sweep on Phase 5 wire-in"
```

If no auto-fixes, skip the commit.

---

### Task 11: Manual visual verification + PR

**Context:** Per CLAUDE.md "For UI or frontend changes, start the dev server and use the feature in a browser before reporting the task as complete." We open one NVDA-style report and confirm: PriceMapCard at top, ActionPlanTable shows badges + evidence, StrategyHeroCard shows hero + alternatives, PositionFlowTimeline shows timeline + grid. Capture a screenshot for the PR.

**Files:** (none modified, but takes a screenshot artifact)

- [ ] **Step 1: Start backend + frontend**

In one shell: `python3.11 main.py --webui-only --port 8000` (per [[repo-fastapi-mode-pkill-grep]]).
In another: `cd apps/dsa-web && npm run dev`.

- [ ] **Step 2: Open a recent report with `fact_bundle` present**

Open `http://localhost:5173/history/13` (or whichever id is the most recent NVDA analysis with a bundle — pick from the `analysis_history` table). Visually confirm:

| Region | Expected |
|---|---|
| Top of report | `PriceMapCard` with current price + level markers + 刷新价格 button |
| Action plan | Each row shows direction emoji, trigger price, expand toggle. Items with `provenance === 'synthesized'` show 🤖 badge; items with `tier === 'discipline_anchor'` show 📌 badge; expanded rows show `narrative` + grouped evidence |
| Strategy | Single `StrategyHeroCard` (no separate `StrategySelector` block above it). Recommended in hero with citation pills (if structured thesis); alternatives below; inapplicable list at bottom |
| Position outcome | `PositionFlowTimeline` with a row per trigger above the 2×2 summary grid |

- [ ] **Step 3: Click "刷新价格" on the PriceMapCard**

Expected: the displayed current price + timestamp update; no console errors. (If the quote endpoint is rate-limited, you'll see a 429 — acceptable, the button just keeps the old value.)

- [ ] **Step 4: Take a screenshot**

Save the full-page screenshot to `docs/superpowers/screenshots/2026-05-25-phase-5-nvda.png` (create the dir if missing).

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/phase-5-frontend-wire-in
gh pr create \
  --base main \
  --title "feat(report): Phase 5 frontend wire-in — mount evidence components into report page" \
  --body "$(cat <<'EOF'
## What changed

Phase 5 of the evidence-grounded decision pipeline ([spec](docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md) Section C/E). Mounts the Phase 4 atomic components into the actual report UI, builds the two missing composites, and retires three superseded components.

### New / modified
- **fix(api):** `toCamelCase` now preserves `dashboard.fact_bundle` snake_case via `stopPaths` — without this every Phase 4 component receives mangled keys
- **types:** `DashboardSection.factBundle` typed; `StrategyChoice` + `strategyThesis` extended with optional evidence fields
- **utils:** `buildPriceMapLevels` derives `PriceMapCard` levels from a `FactBundle`
- **report:** `PriceMapCard` mounted at top of `ReportSummary`
- **report:** `ActionPlanTable` rewrites — renders `EvidenceExpansion`, `provenance` badge, `narrative`, `tier` pill
- **new:** `StrategyHeroCard` (hero + alternatives + citation pills) replaces `StrategyThesis` + `StrategySelector`
- **new:** `PositionFlowTimeline` (trigger timeline + summary grid) replaces `PositionOutcomeSummary`

### Deleted
- `StrategySelector.tsx`, `StrategyThesis.tsx`, `PositionOutcomeSummary.tsx`

## Why
Phase 4 built atomic frontend components but mounted none of them. Phase 5 closes the gap so users see the evidence-grounded UI on the actual report page.

## Verification
- `cd apps/dsa-web && npm run lint` — pass
- `cd apps/dsa-web && npm run build` — pass
- Targeted vitest sweep on changed surface — all green (see task 10)
- Manual visual verification on NVDA report — see [screenshot](docs/superpowers/screenshots/2026-05-25-phase-5-nvda.png)
- Pre-existing baseline flakes in `Shell.test.tsx` / `HomePage.test.tsx` / `LLMChannelEditor.test.tsx` etc. NOT touched by this PR (handoff item #3)

## Risk + rollback
- All new fields on existing types are optional → legacy reports without `factBundle` render unchanged
- Rollback: `git revert <merge>`; the deleted components are recoverable from git history

## Not done
- Phase 6 — feature flag removal + final docs/CHANGELOG sweep (per spec Section E)
- Pre-existing baseline test flakes — separate diagnostic task
EOF
)"
```

- [ ] **Step 6: Verify CI**

Run: `gh pr checks` (after a 30s grace period for CI to kick off)
Expected: `ai-governance`, `backend-gate`, `web-gate` all green. If `web-gate` fails on a baseline-flake test we did not touch, note it on the PR and move on; if it fails on a Phase-5-touched file, fix locally and force-push.

---

## Self-review

**Spec coverage (Section C frontend components):**
- ✅ PriceMapCard mounted (task 4)
- ✅ EvidenceExpansion + EvidenceRef wired via ActionPlanTable + StrategyHeroCard (tasks 5, 6)
- ✅ ActionPlanTable rewrite (task 5)
- ✅ StrategyHeroCard new (task 6)
- ✅ PositionFlowTimeline new (task 7)
- ✅ ReportSummary reorder (tasks 4, 8)
- ✅ Delete superseded components (task 9)
- ✅ Quote endpoint already shipped in Phase 4; `RefreshPriceButton` already embedded inside `PriceMapCard` (no new wiring needed)
- ⚠️ Spec mentions an e2e Playwright NVDA report test — punted to Phase 6 because the repo has no Playwright harness yet; visual verification + targeted vitest substitute (task 11)

**Placeholder scan:** none — every code step shows the full code, every command shows the full invocation, all file paths absolute.

**Type / name consistency check:**
- `factBundle` (typed key on `DashboardSection`) ↔ `useFactBundle(bundle)` ↔ `EvidenceExpansion` `bundle` prop ↔ `ActionPlanTable` `bundle` prop ↔ `StrategyHeroCard` `bundle` prop — all aligned
- `PriceMapLevel` imported from `./PriceMapCard` by `buildPriceMapLevels` — matches Phase 4 export
- `StrategyThesisStructured` defined in Task 2, consumed in Tasks 6 + 8 — matches
- `provenance: 'llm' | 'synthesized'` consistent across `ActionPlanItem`, `StrategyThesisStructured`, badge logic
- `tier: 'discipline_anchor'` consistent across `ActionPlanItem.tier` (CandidateTier union) and badge logic in `ActionPlanTable`

**Boundary correctness:** confirmed `camelcase-keys` `stopPaths` operates on the original (pre-camelize) path, so `'dashboard.fact_bundle'` is the right value. Inner body keys remain snake_case as Phase 4 expects.
