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
