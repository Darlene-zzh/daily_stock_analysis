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
