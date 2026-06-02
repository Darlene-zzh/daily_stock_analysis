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
    // Positive worst case = a profit-protecting stop above cost; shown as a
    // gain (+ prefix, green) rather than a red loss.
    expect(screen.getByText('+12.34 GBP')).toBeInTheDocument();
    expect(screen.getByText('+45.67 GBP')).toBeInTheDocument();
    expect(screen.getByText('1:3.7')).toBeInTheDocument();
    expect(screen.getByText('0.5 股')).toBeInTheDocument();
  });

  it('shows a positive worst case as a green gain (profit-protecting stop)', () => {
    render(<PositionFlowTimeline summary={summary} triggers={[]} />);
    const worst = screen.getByText('+12.34 GBP');
    expect(worst).toHaveClass('text-success');
    expect(worst).not.toHaveClass('text-danger');
  });

  it('shows a negative worst case as a red loss with native minus sign', () => {
    const losing: PositionOutcomeSummary = {
      ...summary,
      worstCaseLossAmount: -8.5,
      riskRewardRatio: '1:2.0',
    };
    render(<PositionFlowTimeline summary={losing} triggers={[]} />);
    const worst = screen.getByText('-8.5 GBP');
    expect(worst).toHaveClass('text-danger');
    expect(worst).not.toHaveClass('text-success');
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

  it('sorts triggers by ascending priority regardless of input order', () => {
    // Regression: original test fixture passed [p=1, p=2] in-order, so the
    // sort line was a no-op. Pass reversed to verify sort actually fires.
    const reversed = [triggers[1], triggers[0]]; // [priority=2, priority=1]
    render(<PositionFlowTimeline summary={summary} triggers={reversed} />);
    const rows = screen.getAllByTestId('flow-trigger-row');
    expect(rows[0]).toHaveTextContent('$226.13'); // priority 1 first
    expect(rows[1]).toHaveTextContent('$213.40'); // priority 2 second
  });

  it('omits the summary grid when summary is empty but triggers exist', () => {
    render(
      <PositionFlowTimeline summary={{} as PositionOutcomeSummary} triggers={triggers} />,
    );
    // Triggers render (the timeline)
    expect(screen.getAllByTestId('flow-trigger-row')).toHaveLength(2);
    // Grid labels do NOT appear — avoids a useless `— / — / — / —` block
    expect(screen.queryByText('执行所有触发后剩余')).not.toBeInTheDocument();
    expect(screen.queryByText('风险回报比')).not.toBeInTheDocument();
  });
});
