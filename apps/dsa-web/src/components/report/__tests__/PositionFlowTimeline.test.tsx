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
