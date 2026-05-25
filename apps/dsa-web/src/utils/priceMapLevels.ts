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
    // 'entry' direction is intentionally omitted — PriceMapRole has no 'entry'
    // slot; entries are surfaced inside ActionPlanTable instead of on the axis.
  }

  return out;
}
