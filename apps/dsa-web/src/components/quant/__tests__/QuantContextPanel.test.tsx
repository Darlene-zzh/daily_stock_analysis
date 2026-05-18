import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { QuantContextPanel } from '../QuantContextPanel';
import type { QuantSignalResponse } from '../../../api/quantSignal';

const sampleFactors = {
  stockCode: '600519',
  market: 'cn',
  asOf: '2026-05-18',
  quantiles: {
    ret_5d: 0.012,
    ret_20d: 0.045,
    volume_ratio_20d: 0.62,
  },
};

const sampleForecast = {
  stockCode: '600519',
  market: 'cn',
  asOf: '2026-05-18',
  horizonDays: 10,
  expectedExcessReturn: 0.0182,
  rankInUniverse: 0.84,
  icCurrent: 0.045,
  icMa4w: 0.038,
  modelVersion: '2026-W20',
};

describe('QuantContextPanel', () => {
  it('renders nothing when the backend has no signal (initialData=null)', () => {
    const { container } = render(
      <QuantContextPanel stockCode="600519" initialData={null} language="zh" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders factor strip + forecast banner + caveat when data is full', () => {
    const data: QuantSignalResponse = {
      stockCode: '600519',
      market: 'cn',
      horizonDays: 10,
      factors: sampleFactors,
      forecast: sampleForecast,
    };
    render(
      <QuantContextPanel
        stockCode="600519"
        initialData={data}
        language="zh"
      />,
    );
    expect(screen.getByTestId('quant-context-panel')).toBeInTheDocument();
    expect(screen.getByTestId('quant-context-caveat')).toBeInTheDocument();
    expect(screen.getByTestId('quant-factor-ret_5d')).toBeInTheDocument();
    expect(screen.getByTestId('quant-factor-ret_20d')).toBeInTheDocument();
    // Forecast values rendered
    expect(screen.getByText('+0.0182')).toBeInTheDocument();
    expect(screen.getByText('2026-W20')).toBeInTheDocument();
  });

  it('shows "model uncertain" tag when factors present but forecast null', () => {
    const data: QuantSignalResponse = {
      stockCode: '600519',
      market: 'cn',
      horizonDays: 10,
      factors: sampleFactors,
      forecast: null,
    };
    render(
      <QuantContextPanel
        stockCode="600519"
        initialData={data}
        language="zh"
      />,
    );
    expect(screen.getByTestId('quant-context-uncertain')).toBeInTheDocument();
    expect(screen.getByTestId('quant-context-panel')).toBeInTheDocument();
  });

  it('renders the English copy when language="en"', () => {
    const data: QuantSignalResponse = {
      stockCode: 'AAPL',
      market: 'us',
      horizonDays: 10,
      factors: sampleFactors,
      forecast: sampleForecast,
    };
    render(
      <QuantContextPanel
        stockCode="AAPL"
        initialData={data}
        language="en"
      />,
    );
    expect(screen.getByText('Quant Context (auxiliary)')).toBeInTheDocument();
    // Caveat must contain the "NOT a recommendation" line
    expect(
      screen.getByTestId('quant-context-caveat').textContent || '',
    ).toMatch(/NOT a buy\/sell recommendation/);
  });

  it('uses the injected api when no initialData is supplied', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      stockCode: '600519',
      market: 'cn',
      horizonDays: 10,
      factors: sampleFactors,
      forecast: null,
    });
    const apiMock = { fetch: fetchMock } as never;
    render(
      <QuantContextPanel stockCode="600519" api={apiMock} language="zh" />,
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('600519', {
        market: undefined,
        horizon: undefined,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId('quant-context-panel')).toBeInTheDocument();
    });
  });

  it('renders nothing when the api returns null (204 No Content)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(null);
    const apiMock = { fetch: fetchMock } as never;
    const { container } = render(
      <QuantContextPanel stockCode="600519" api={apiMock} language="zh" />,
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    // After resolve the panel renders null
    await waitFor(() => {
      expect(container.querySelector('[data-testid="quant-context-panel"]')).toBeNull();
    });
  });
});
