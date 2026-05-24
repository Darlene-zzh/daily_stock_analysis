import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceExpansion } from '../EvidenceExpansion';
import type { FactBundle } from '../../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-24T10:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    {
      id: 'technical.resistance',
      type: 'technical',
      label: '阻力位',
      value: 226.13,
      display_value: '$226.13 阻力位',
    },
    {
      id: 'technical.rsi_12',
      type: 'technical',
      label: 'RSI(12)',
      value: 71.1,
      display_value: 'RSI(12) = 71.1 (超买)',
    },
    {
      id: 'committee.pm_verdict',
      type: 'committee',
      label: 'PM 裁决',
      value: 'hold',
      display_value: 'PM hold (5.8/10)',
    },
    {
      id: 'quant.score',
      type: 'quant',
      label: '量化评分',
      value: 0.62,
      display_value: '量化评分 0.62',
    },
  ],
  candidates: [],
};

describe('EvidenceExpansion', () => {
  it('renders nothing when evidenceRefs is empty', () => {
    const { container } = render(
      <EvidenceExpansion evidenceRefs={[]} bundle={bundle} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when bundle is missing', () => {
    const { container } = render(
      <EvidenceExpansion evidenceRefs={['technical.rsi_12']} bundle={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('groups refs by type when groupBy="type" (default)', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={[
          'technical.rsi_12',
          'committee.pm_verdict',
          'technical.resistance',
        ]}
        bundle={bundle}
      />,
    );
    // Two group headers visible
    expect(screen.getByText(/技术/i)).toBeInTheDocument();
    expect(screen.getByText(/委员会/i)).toBeInTheDocument();
  });

  it('renders refs flat when groupBy="flat"', () => {
    const { container } = render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'committee.pm_verdict']}
        bundle={bundle}
        groupBy="flat"
      />,
    );
    // No group headers; pills appear sequentially
    expect(container.querySelectorAll('[data-evidence-group]').length).toBe(0);
  });

  it('expands a group when its header is clicked', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12']}
        bundle={bundle}
      />,
    );
    const header = screen.getByRole('button', { name: /技术/i });
    // Default collapsed — display_value not visible
    expect(screen.queryByText('RSI(12) = 71.1 (超买)')).not.toBeInTheDocument();
    fireEvent.click(header);
    expect(screen.getByText('RSI(12) = 71.1 (超买)')).toBeInTheDocument();
  });

  it('respects defaultOpen prop', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12']}
        bundle={bundle}
        defaultOpen={['technical']}
      />,
    );
    expect(screen.getByText('RSI(12) = 71.1 (超买)')).toBeInTheDocument();
  });

  it('renders a fallback pill for refs that miss the bundle', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'unknown.fact_id']}
        bundle={bundle}
        defaultOpen={['technical', 'unknown']}
      />,
    );
    expect(screen.getByText(/unknown.fact_id/)).toBeInTheDocument();
  });

  it('dedupes repeated refs', () => {
    render(
      <EvidenceExpansion
        evidenceRefs={['technical.rsi_12', 'technical.rsi_12']}
        bundle={bundle}
        defaultOpen={['technical']}
      />,
    );
    const pills = screen.getAllByText('RSI(12)');
    expect(pills).toHaveLength(1);
  });
});
