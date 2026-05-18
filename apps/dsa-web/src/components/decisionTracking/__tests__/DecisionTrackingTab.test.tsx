import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DecisionTrackingTab } from '../DecisionTrackingTab';
import type { DecisionJournalEntry } from '../../../api/decisionJournal';

const sample: DecisionJournalEntry = {
  decisionAt: '2026-05-10 09:00:00',
  priceAtDecision: 100,
  reportLanguage: 'zh',
  verdict: '买入',
  score: 72,
  oneSentence: 'AI 加速器需求强劲，利润率正在企稳。',
  committeePmVerdict: null,
  keyCatalysts: ['Cloud monetisation'],
  keyRisks: ['Margin compression'],
  analysisQueryId: 'q-1',
  rawReturn: 0.08,
  benchmarkReturn: 0.03,
  alpha: 0.05,
};

const sampleNoBenchmark: DecisionJournalEntry = {
  ...sample,
  decisionAt: '2026-04-10 09:00:00',
  rawReturn: 0.04,
  benchmarkReturn: null,
  alpha: null,
};

describe('DecisionTrackingTab', () => {
  it('renders the empty state when no entries are available', () => {
    render(
      <DecisionTrackingTab stockCode="600519" initialEntries={[]} language="zh" />,
    );
    expect(screen.getByTestId('decision-tracking-empty')).toBeInTheDocument();
  });

  it('renders rows + sparkline when entries are present', () => {
    render(
      <DecisionTrackingTab
        stockCode="600519"
        initialEntries={[sample]}
        language="zh"
      />,
    );
    expect(screen.getByTestId('decision-tracking-tab')).toBeInTheDocument();
    expect(screen.getByText('买入')).toBeInTheDocument();
    expect(screen.getByText('+8.00%')).toBeInTheDocument();
    expect(screen.getByText('+5.00%')).toBeInTheDocument();
    expect(screen.getByTestId('alpha-sparkline')).toBeInTheDocument();
  });

  it('falls back to em dash when alpha is unavailable', () => {
    render(
      <DecisionTrackingTab
        stockCode="600519"
        initialEntries={[sampleNoBenchmark]}
        language="en"
      />,
    );
    expect(screen.getByText('+4.00%')).toBeInTheDocument();
    // ``—`` is the placeholder for alpha
    const alphaCell = screen.getAllByText('—');
    expect(alphaCell.length).toBeGreaterThan(0);
  });

  it('calls the API client when no initialEntries are provided', async () => {
    const apiMock = {
      list: vi.fn().mockResolvedValue({
        stockCode: '600519',
        market: 'cn',
        count: 1,
        entries: [sample],
      }),
    };
    render(
      <DecisionTrackingTab stockCode="600519" api={apiMock as never} language="en" />,
    );
    await waitFor(() => {
      expect(apiMock.list).toHaveBeenCalledWith('600519', {
        market: undefined,
        limit: 20,
      });
    });
    expect(await screen.findByTestId('decision-tracking-tab')).toBeInTheDocument();
    expect(screen.getByText('Alpha trend (oldest → newest)')).toBeInTheDocument();
  });

  it('renders the error pane when the fetch fails', async () => {
    const apiMock = {
      list: vi.fn().mockRejectedValue(new Error('boom')),
    };
    render(
      <DecisionTrackingTab stockCode="600519" api={apiMock as never} language="en" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('decision-tracking-error')).toBeInTheDocument();
    });
  });
});
