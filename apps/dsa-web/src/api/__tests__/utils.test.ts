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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.coreConclusion.recommendedStrategy).toBe('swing_trade');
    // factBundle is the camelized outer key — but its body is preserved
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.as_of).toBe('2026-05-25T00:00:00Z');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.stock_code).toBe('NVDA');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.facts[0].display_value).toBe('$226.13');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.facts[0].basis_fact_id).toBe('technical.resistance');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.candidates[0].basis_rule).toBe('resistance_touch');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).dashboard.factBundle.candidates[0].applicable_strategies).toEqual(['swing_trade']);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).report.dashboard.factBundle.stock_code).toBe('AAPL');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((out as any).report.dashboard.factBundle.facts[0].display_value).toBe('1');
  });
});
