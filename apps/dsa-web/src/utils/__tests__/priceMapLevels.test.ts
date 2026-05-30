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
  it('emits technical.support but NOT MAs (MA5/10/20 are meta-indicators)', () => {
    const out = buildPriceMapLevels(bundle);
    expect(out.find((l) => l.factId === 'technical.ma5')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.ma10')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.ma20')).toBeUndefined();
    const support = out.find((l) => l.factId === 'technical.support');
    expect(support).toMatchObject({ role: 'support', color: 'green' });
  });

  it('emits primary-tier candidates with stop/target roles and short rule-based labels', () => {
    const out = buildPriceMapLevels(bundle);
    const stop = out.find((l) => l.factId === 'candidate.stop.1');
    expect(stop).toMatchObject({ role: 'stop', color: 'red', price: 213.39, label: '跌破MA20' });
    const target = out.find((l) => l.factId === 'candidate.exit.1');
    expect(target).toMatchObject({ role: 'target', color: 'green', price: 226.13, label: '阻力位' });
  });

  it('dedupes technical.resistance when a candidate already references it via basis_fact_id', () => {
    // candidate.exit.1 has basis_fact_id='technical.resistance' → fact must be omitted
    const out = buildPriceMapLevels(bundle);
    expect(out.find((l) => l.factId === 'technical.resistance')).toBeUndefined();
    // But the candidate IS present
    expect(out.find((l) => l.factId === 'candidate.exit.1')).toBeDefined();
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

  it('silently drops primary-tier entry candidates (no PriceMapRole slot for entries)', () => {
    const entryOnly: FactBundle = {
      ...bundle,
      candidates: [
        { id: 'candidate.entry.1', type: 'candidate', label: 'MA10 回踩买点', value: 222.02,
          display_value: '$222.02', direction: 'entry', price: 222.02,
          basis_fact_id: 'technical.ma10', basis_rule: 'ma10_pullback',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -0.65 },
      ],
    };
    const out = buildPriceMapLevels(entryOnly);
    expect(out.find((l) => l.factId === 'candidate.entry.1')).toBeUndefined();
  });

  it('discards facts with non-numeric or non-finite value via the Number.isFinite guard', () => {
    const noisy: FactBundle = {
      ...bundle,
      facts: [
        { id: 'technical.support', type: 'technical', label: '支撑', value: 'not-a-number', display_value: '—' },
        { id: 'technical.resistance', type: 'technical', label: '阻力', value: 0, display_value: '0' },
      ],
      candidates: [],  // empty → no candidate dedupe; tests fact guard only
    };
    const out = buildPriceMapLevels(noisy);
    expect(out.find((l) => l.factId === 'technical.support')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.resistance')).toBeUndefined();
  });

  it('dedupes two candidates at the same price (within 0.3%) keeping higher rule priority', () => {
    // Real-world case: resistance_touch + prev_swing_high both land on 218.95.
    // resistance_touch has rule priority 10, prev_swing_high has 12 → keep
    // resistance_touch ("阻力位") and drop prev_swing_high ("前高").
    const collision: FactBundle = {
      ...bundle,
      candidates: [
        { id: 'candidate.exit.resistance', type: 'candidate', label: 'R', value: 218.95,
          display_value: '$218.95', direction: 'take_profit', price: 218.95,
          basis_fact_id: 'technical.resistance', basis_rule: 'resistance_touch',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: 1.0 },
        { id: 'candidate.exit.prev_high', type: 'candidate', label: 'PH', value: 218.95,
          display_value: '$218.95', direction: 'take_profit', price: 218.95,
          basis_fact_id: 'technical.prev_high', basis_rule: 'prev_swing_high',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: 1.0 },
      ],
    };
    const out = buildPriceMapLevels(collision);
    const targets = out.filter((l) => l.role === 'target');
    expect(targets).toHaveLength(1);
    expect(targets[0].factId).toBe('candidate.exit.resistance');
    expect(targets[0].label).toBe('阻力位');
  });

  it('drops technical.support when a candidate price is within 0.3% (visual dup)', () => {
    // ma20_breakdown 185.24 + technical.support 185.21 → support should drop
    // even though it has no basis_fact_id collision.
    const closeFacts: FactBundle = {
      as_of: '', market: 'us', stock_code: 'X',
      facts: [
        { id: 'technical.support', type: 'technical', label: '支撑位', value: 185.21,
          display_value: '$185.21' },
      ],
      candidates: [
        { id: 'candidate.stop.ma20', type: 'candidate', label: 'MA20', value: 185.24,
          display_value: '$185.24', direction: 'stop_loss', price: 185.24,
          basis_fact_id: 'technical.ma20', basis_rule: 'ma20_breakdown',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -5 },
      ],
    };
    const out = buildPriceMapLevels(closeFacts);
    expect(out.find((l) => l.factId === 'technical.support')).toBeUndefined();
    expect(out.find((l) => l.factId === 'candidate.stop.ma20')).toBeDefined();
  });

  it('caps stops to MAX_STOPS (2) closest to current price by |distance|', () => {
    const manyStops: FactBundle = {
      ...bundle,
      candidates: [
        { id: 'candidate.stop.a', type: 'candidate', label: 'A', value: 0, display_value: '',
          direction: 'stop_loss', price: 215, basis_fact_id: '', basis_rule: 'ma20_breakdown',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -2 },
        { id: 'candidate.stop.b', type: 'candidate', label: 'B', value: 0, display_value: '',
          direction: 'stop_loss', price: 200, basis_fact_id: '', basis_rule: 'support_breakdown',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -8 },
        { id: 'candidate.stop.c', type: 'candidate', label: 'C', value: 0, display_value: '',
          direction: 'stop_loss', price: 180, basis_fact_id: '', basis_rule: 'atr_3x_below_current',
          applicable_strategies: ['swing_trade'], tier: 'primary', distance_pct_from_current: -15 },
      ],
    };
    const out = buildPriceMapLevels(manyStops);
    const stopIds = out.filter((l) => l.role === 'stop').map((l) => l.factId);
    expect(stopIds).toHaveLength(2);
    expect(stopIds).toContain('candidate.stop.a');  // closest
    expect(stopIds).toContain('candidate.stop.b');  // 2nd closest
    expect(stopIds).not.toContain('candidate.stop.c');  // dropped (farthest)
  });
});
