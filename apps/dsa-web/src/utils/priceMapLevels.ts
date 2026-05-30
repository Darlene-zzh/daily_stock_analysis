import type { FactBundle, CandidateLevel } from '../types/analysis';
import type { PriceMapLevel } from '../components/report/PriceMapCard';

/**
 * Technical facts surfaced on the price axis. MA5/MA10/MA20 are intentionally
 * EXCLUDED — moving averages are meta-indicators that the candidates already
 * encode via basis_rule (e.g. `ma20_breakdown` shows the same price MA20 does,
 * with the directional intent attached). Showing both produces overlap.
 *
 * Support / resistance are kept here as separate pivot markers since they
 * carry semantic weight independent of any stop/target action — but they will
 * be deduped against candidates by basis_fact_id AND by price proximity below.
 */
const TECHNICAL_LEVEL_FACTS: Record<
  string,
  { role: PriceMapLevel['role']; color: PriceMapLevel['color']; label: string }
> = {
  'technical.support':    { role: 'support',    color: 'green',  label: '支撑' },
  'technical.resistance': { role: 'resistance', color: 'orange', label: '阻力' },
};

const MAX_STOPS = 2;
const MAX_TARGETS = 3;

/**
 * Two markers within this fraction of each other (0.3%) are considered the
 * "same price" for dedupe purposes. Real bundles routinely have e.g.
 * resistance_touch + prev_swing_high at the exact same price.
 */
const PRICE_DEDUPE_TOLERANCE = 0.003;

const RULE_SHORT_LABEL: Record<string, string> = {
  ma20_breakdown:        '跌破MA20',
  support_breakdown:     '跌破支撑',
  prev_swing_low:        '前低',
  atr_2x_below_current:  '-2×ATR',
  atr_3x_below_current:  '-3×ATR',
  cost_minus_10pct:      'cost-10%',
  resistance_touch:      '阻力位',
  resistance_plus_atr:   '阻力+ATR',
  prev_swing_high:       '前高',
  r_multiple_2r:         '2R',
  r_multiple_3r:         '3R',
  fib_extension_1272:    'Fib1.272',
  fib_extension_1618:    'Fib1.618',
  psychological_round:   '心理位',
};

/**
 * Rule preference when two candidates collide at the same price. Lower number
 * wins. The picks reflect "which label gives the user the most actionable
 * narrative" — structure-based rules (MA20, support, resistance) outrank
 * statistical extensions (ATR multiples, Fib).
 */
const RULE_PRIORITY: Record<string, number> = {
  ma20_breakdown:        10,
  support_breakdown:     11,
  resistance_touch:      10,
  prev_swing_high:       12,
  prev_swing_low:        12,
  r_multiple_2r:         15,
  r_multiple_3r:         16,
  resistance_plus_atr:   18,
  fib_extension_1272:    20,
  fib_extension_1618:    21,
  psychological_round:   25,
  atr_2x_below_current:  30,
  atr_3x_below_current:  31,
  cost_minus_10pct:      40,
};

function shortLabel(cand: CandidateLevel): string {
  return RULE_SHORT_LABEL[cand.basis_rule] ?? cand.label;
}

function rulePriority(cand: CandidateLevel): number {
  return RULE_PRIORITY[cand.basis_rule] ?? 99;
}

function pricesClose(a: number, b: number): boolean {
  if (a <= 0 || b <= 0) return false;
  return Math.abs(a - b) / Math.max(a, b) < PRICE_DEDUPE_TOLERANCE;
}

/**
 * Drop candidates whose price collides with a higher-priority candidate of the
 * same direction (within PRICE_DEDUPE_TOLERANCE). Preserves the input order
 * for survivors so the caller's slice/cap logic remains predictable.
 */
function dedupeByPrice(cands: CandidateLevel[]): CandidateLevel[] {
  const sorted = [...cands].sort((a, b) => rulePriority(a) - rulePriority(b));
  const kept: CandidateLevel[] = [];
  for (const c of sorted) {
    if (kept.some((k) => pricesClose(k.price, c.price))) continue;
    kept.push(c);
  }
  // Return in original input order for stable downstream sort.
  const keptIds = new Set(kept.map((k) => k.id));
  return cands.filter((c) => keptIds.has(c.id));
}

/**
 * Build the `levels[]` prop for `PriceMapCard` from a FactBundle.
 *
 * Selection rules (ordered):
 *   1. Per-direction: dedupe primary candidates by price (within 0.3%),
 *      keeping the higher-priority rule; sort by |distance|; cap to MAX_*.
 *   2. Collect basis_fact_ids referenced by surviving candidates + the
 *      surviving candidate prices.
 *   3. Add technical.support / technical.resistance ONLY IF (a) not referenced
 *      by a candidate's basis_fact_id AND (b) not within 0.3% of any survivor
 *      candidate price (avoids visual duplicates).
 *
 * Skips: current_price, RSI, MA5/MA10/MA20 facts, candidate entries, secondary
 * / discipline_anchor candidates.
 */
export function buildPriceMapLevels(bundle: FactBundle | null | undefined): PriceMapLevel[] {
  if (!bundle) return [];

  const out: PriceMapLevel[] = [];
  const primaryCands = bundle.candidates.filter((c) => c.tier === 'primary');

  // Stops: dedupe by price, sort by |distance|, cap.
  const rawStops = primaryCands.filter(
    (c) => c.direction === 'stop_loss' || c.direction === 'stop',
  );
  const stops = dedupeByPrice(rawStops)
    .sort((a, b) => Math.abs(a.distance_pct_from_current) - Math.abs(b.distance_pct_from_current))
    .slice(0, MAX_STOPS);
  for (const c of stops) {
    out.push({ factId: c.id, price: c.price, label: shortLabel(c), color: 'red', role: 'stop' });
  }

  // Targets: dedupe by price, sort by |distance|, cap.
  const rawTargets = primaryCands.filter(
    (c) => c.direction === 'take_profit' || c.direction === 'exit',
  );
  const targets = dedupeByPrice(rawTargets)
    .sort((a, b) => Math.abs(a.distance_pct_from_current) - Math.abs(b.distance_pct_from_current))
    .slice(0, MAX_TARGETS);
  for (const c of targets) {
    out.push({ factId: c.id, price: c.price, label: shortLabel(c), color: 'green', role: 'target' });
  }

  // Dedupe technical pivots:
  //   (a) skip if any candidate's basis_fact_id already references this fact
  //   (b) skip if fact price collides with any surviving candidate price
  const referencedFactIds = new Set<string>(
    [...stops, ...targets].map((c) => c.basis_fact_id).filter(Boolean),
  );
  const survivorPrices = [...stops, ...targets].map((c) => c.price);

  for (const fact of bundle.facts) {
    const cfg = TECHNICAL_LEVEL_FACTS[fact.id];
    if (!cfg) continue;
    if (referencedFactIds.has(fact.id)) continue;
    const price = typeof fact.value === 'number' ? fact.value : Number(fact.value);
    if (!Number.isFinite(price) || price <= 0) continue;
    if (survivorPrices.some((p) => pricesClose(p, price))) continue;
    out.push({ factId: fact.id, price, label: cfg.label, color: cfg.color, role: cfg.role });
  }
  // 'entry' direction intentionally omitted — entries are surfaced inside
  // ActionPlanTable, not on the price axis (no PriceMapRole slot for entries).

  return out;
}
