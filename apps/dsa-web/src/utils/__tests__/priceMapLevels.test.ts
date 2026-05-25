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
        { id: 'technical.ma10', type: 'technical', label: 'MA10', value: 'not-a-number', display_value: '—' },
        { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 0, display_value: '0' },
        { id: 'technical.resistance', type: 'technical', label: '阻力位', value: 226.13, display_value: '$226.13' },
      ],
      candidates: [],
    };
    const out = buildPriceMapLevels(noisy);
    expect(out.find((l) => l.factId === 'technical.ma10')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.ma20')).toBeUndefined();
    expect(out.find((l) => l.factId === 'technical.resistance')).toMatchObject({ price: 226.13 });
  });
});
