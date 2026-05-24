import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PriceMapCard } from '../PriceMapCard';

const baseLevels = [
  { factId: 'technical.support', price: 215.5, label: '支撑', color: 'green' as const, role: 'support' as const },
  { factId: 'technical.resistance', price: 226.13, label: '阻力', color: 'red' as const, role: 'resistance' as const },
  { factId: 'technical.ma20', price: 220.0, label: 'MA20', color: 'blue' as const, role: 'ma' as const },
];

describe('PriceMapCard', () => {
  it('renders nothing when levels is empty', () => {
    const { container } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={[]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the current price prominently', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    expect(screen.getByText(/220\.5/)).toBeInTheDocument();
  });

  it('renders a marker per level with its label', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    for (const lvl of baseLevels) {
      expect(screen.getByText(lvl.label)).toBeInTheDocument();
    }
  });

  it('renders distance % from current price for each level', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    // Resistance is +2.55% (226.13 vs 220.5)
    expect(screen.getByText(/\+2\.5\d%/)).toBeInTheDocument();
    // Support is -2.27% (215.5 vs 220.5)
    expect(screen.getByText(/-2\.2\d%/)).toBeInTheDocument();
  });

  it('renders the RefreshPriceButton when onRefresh is not provided', () => {
    render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    // Default refresh button (uses stocksApi)
    expect(screen.getByRole('button', { name: /刷新/i })).toBeInTheDocument();
  });

  it('calls the supplied onRefresh callback and updates displayed price', async () => {
    const onRefresh = vi.fn().mockResolvedValue({ price: 222.0, asOf: '2026-05-24T11:00:00Z' });
    const { findByText, getByRole } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={220.5}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
        onRefresh={onRefresh}
      />,
    );
    getByRole('button', { name: /刷新/i }).click();
    expect(onRefresh).toHaveBeenCalled();
    // After refresh, displayed price updates to 222.0
    expect(await findByText(/222(\.|0)/)).toBeInTheDocument();
  });

  it('renders nothing when currentPrice is 0 or negative (invalid input)', () => {
    const { container } = render(
      <PriceMapCard
        stockCode="NVDA"
        currentPrice={0}
        currentPriceAsOf="2026-05-24T10:00:00Z"
        levels={baseLevels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
