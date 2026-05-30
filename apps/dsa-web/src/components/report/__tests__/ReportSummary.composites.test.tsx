import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReportSummary } from '../ReportSummary';
import type { AnalysisReport } from '../../../types/analysis';

vi.mock('../../committee/CommitteeMinutesPanel', () => ({ CommitteeMinutesPanel: () => null }));
vi.mock('../../decisionTracking/DecisionTrackingTab', () => ({ DecisionTrackingTab: () => null }));
vi.mock('../../quant/QuantContextPanel', () => ({ QuantContextPanel: () => null }));
vi.mock('../../risk/StructuredRiskCallout', () => ({ StructuredRiskCallout: () => null }));
vi.mock('../ReportNews', () => ({ ReportNews: () => null }));
vi.mock('../ReportOverview', () => ({ ReportOverview: () => <div /> }));
vi.mock('../ReportDetails', () => ({ ReportDetails: () => null }));
vi.mock('../ReportStrategy', () => ({ ReportStrategy: () => null }));

function buildReport(): AnalysisReport {
  return {
    meta: { id: 'r', stockCode: 'NVDA', stockName: 'NVIDIA', market: 'us', generatedAt: '' } as unknown as AnalysisReport['meta'],
    summary: {} as AnalysisReport['summary'],
    dashboard: {
      coreConclusion: {
        actionPlanItems: [],
        strategyChoices: [
          { id: 'swing_trade', labelZh: '短线波段', emoji: '⚡', applicable: true, fitCondition: 'fit' },
        ],
        recommendedStrategy: 'swing_trade',
        strategyThesis: 'thesis text',
        positionOutcomeSummary: { riskRewardRatio: '1:2', worstCaseLossAmount: 10, bestCaseGainAmount: 20, worstCaseCurrency: 'USD' },
      },
    },
  };
}

describe('ReportSummary — composite swap', () => {
  it('renders StrategyHeroCard instead of StrategySelector + StrategyThesis', () => {
    render(<ReportSummary data={buildReport()} />);
    expect(screen.getByText(/AI 推荐策略：⚡ 短线波段/)).toBeInTheDocument();
    expect(screen.getByText('thesis text')).toBeInTheDocument();
    // Old separate "📌 策略选择" header from StrategySelector should be gone
    expect(screen.queryByText('📌 策略选择')).not.toBeInTheDocument();
  });

  it('renders PositionFlowTimeline (with summary grid)', () => {
    render(<ReportSummary data={buildReport()} />);
    expect(screen.getByText('📊 仓位流水汇总')).toBeInTheDocument();
    expect(screen.getByText('1:2')).toBeInTheDocument();
  });
});
