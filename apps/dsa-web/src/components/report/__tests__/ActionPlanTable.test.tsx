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

  it('hides the expand toggle entirely when item has no basis, narrative, or evidence', () => {
    const bare: ActionPlanItem = {
      ...baseItem(),
      invalidationRule: '',
      technicalBasis: '',
      fundamentalBasis: '',
      quantSignal: '',
    };
    render(<ActionPlanTable items={[bare]} />);
    expect(screen.queryByText(/查看分析依据/)).not.toBeInTheDocument();
  });

  it('does NOT render EvidenceExpansion when evidenceRefs is an empty array (bundle present)', () => {
    render(
      <ActionPlanTable bundle={bundle} items={[baseItem({ evidenceRefs: [] })]} />,
    );
    // Toggle still shows because invalidationRule is set in baseItem
    fireEvent.click(screen.getByText(/查看分析依据/));
    expect(screen.queryByText(/技术（/)).not.toBeInTheDocument();
  });

  it('does NOT render 🤖 代码兜底 badge when provenance is llm', () => {
    render(<ActionPlanTable items={[baseItem({ provenance: 'llm' })]} />);
    expect(screen.queryByText(/代码兜底/)).not.toBeInTheDocument();
  });
});
