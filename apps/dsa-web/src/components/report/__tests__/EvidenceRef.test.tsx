import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceRef } from '../EvidenceRef';
import type { FactRecord } from '../../../types/analysis';

const sampleFact: FactRecord = {
  id: 'technical.resistance',
  type: 'technical',
  label: '阻力位',
  value: 226.13,
  display_value: '$226.13',
  source: 'data_perspective.technical',
};

describe('EvidenceRef', () => {
  it('renders a pill with the fact label', () => {
    render(<EvidenceRef fact={sampleFact} />);
    expect(screen.getByText('阻力位')).toBeInTheDocument();
  });

  it('exposes display_value in a title attribute for hover tooltip', () => {
    render(<EvidenceRef fact={sampleFact} />);
    const pill = screen.getByText('阻力位');
    expect(pill.closest('[title]')).toHaveAttribute('title', '$226.13');
  });

  it('renders nothing when fact is undefined', () => {
    const { container } = render(<EvidenceRef fact={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('accepts a fallback id when fact is missing but id is known', () => {
    const { container } = render(
      <EvidenceRef fact={undefined} fallbackId="quant.score" />,
    );
    // Fallback renders the raw id so reviewers can see what's referenced
    expect(container.textContent).toContain('quant.score');
  });

  it('forwards className to the root element', () => {
    const { container } = render(
      <EvidenceRef fact={sampleFact} className="custom-pill" />,
    );
    expect(container.querySelector('.custom-pill')).not.toBeNull();
  });
});
