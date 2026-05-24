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
