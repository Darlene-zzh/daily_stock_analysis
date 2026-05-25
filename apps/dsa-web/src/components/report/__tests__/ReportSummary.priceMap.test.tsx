import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReportSummary } from '../ReportSummary';
import type { AnalysisReport, FactBundle } from '../../../types/analysis';

// Stub the children components that pull in heavy deps (charts, contexts) so
// the test focuses on PriceMapCard wiring.
vi.mock('../../committee/CommitteeMinutesPanel', () => ({ CommitteeMinutesPanel: () => null }));
vi.mock('../../decisionTracking/DecisionTrackingTab', () => ({ DecisionTrackingTab: () => null }));
vi.mock('../../quant/QuantContextPanel', () => ({ QuantContextPanel: () => null }));
vi.mock('../../risk/StructuredRiskCallout', () => ({ StructuredRiskCallout: () => null }));
vi.mock('../ReportNews', () => ({ ReportNews: () => null }));
vi.mock('../ReportOverview', () => ({ ReportOverview: () => <div data-testid="overview" /> }));
vi.mock('../ReportDetails', () => ({ ReportDetails: () => null }));
vi.mock('../ReportStrategy', () => ({ ReportStrategy: () => null }));

const factBundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.current_price', type: 'technical', label: '现价', value: 223.47, display_value: '$223.47' },
    { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 213.40, display_value: '$213.40' },
    { id: 'technical.resistance', type: 'technical', label: '阻力位', value: 226.13, display_value: '$226.13' },
  ],
  candidates: [],
};

function buildReport(opts: { withBundle: boolean }): AnalysisReport {
  return {
    meta: {
      id: 'rec-1',
      stockCode: 'NVDA',
      stockName: 'NVIDIA',
      market: 'us',
      generatedAt: '2026-05-25T00:00:00Z',
    } as unknown as AnalysisReport['meta'],
    summary: {} as AnalysisReport['summary'],
    dashboard: opts.withBundle ? { factBundle } : undefined,
  };
}

describe('ReportSummary + PriceMapCard wire-in', () => {
  it('mounts PriceMapCard when a factBundle with current_price is present', () => {
    render(<ReportSummary data={buildReport({ withBundle: true })} />);
    expect(screen.getByTestId('overview')).toBeInTheDocument();
    expect(document.querySelector('[data-component="price-map-card"]')).not.toBeNull();
  });

  it('does NOT mount PriceMapCard when factBundle is absent (legacy report)', () => {
    render(<ReportSummary data={buildReport({ withBundle: false })} />);
    expect(document.querySelector('[data-component="price-map-card"]')).toBeNull();
  });
});
