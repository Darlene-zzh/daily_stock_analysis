import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  StructuredRiskCallout,
  type StructuredRiskAssessment,
} from '../StructuredRiskCallout';

describe('StructuredRiskCallout', () => {
  it('renders nothing when no risk assessment payload is attached', () => {
    const { container } = render(
      <StructuredRiskCallout riskAssessment={null} language="zh" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the prop is undefined (default state)', () => {
    const { container } = render(<StructuredRiskCallout language="zh" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders severity badge + position pct + tail-risk + VaR (ZH)', () => {
    const payload: StructuredRiskAssessment = {
      severity: 'soft',
      redFlags: ['EPS miss', 'Lockup unlock in 14 days'],
      suggestedPositionPct: 0.12,
      veto: false,
      tailRiskScore: 6.5,
      varEstimate5pct: 0.034,
      volatilityAnnualised: 0.32,
      rationale: 'Mixed signals; weight cautiously.',
    };
    render(<StructuredRiskCallout riskAssessment={payload} language="zh" />);
    // Top-level container renders
    expect(screen.getByTestId('structured-risk-callout')).toBeInTheDocument();
    // Severity badge carries the soft tier
    const severity = screen.getByTestId('structured-risk-severity');
    expect(severity.textContent).toContain('soft');
    expect(severity.textContent).not.toContain('veto');
    // Position pct rendered as percentage
    expect(screen.getByTestId('structured-risk-position').textContent).toBe('12.0%');
    // Tail-risk score in '/10' form
    expect(screen.getByTestId('structured-risk-tail').textContent).toBe('6.50 / 10');
    // VaR formatted with 2 dp percentage
    expect(screen.getByTestId('structured-risk-var').textContent).toBe('3.40%');
    expect(screen.getByTestId('structured-risk-vol').textContent).toBe('32.0%');
    // Red flags list each as separate li
    expect(screen.getAllByTestId('structured-risk-flag')).toHaveLength(2);
    // Rationale rendered as a quote
    expect(screen.getByTestId('structured-risk-rationale')).toBeInTheDocument();
  });

  it('shows veto=true when severity=hard and veto flag set (EN)', () => {
    const payload: StructuredRiskAssessment = {
      severity: 'hard',
      redFlags: ['Regulatory probe'],
      suggestedPositionPct: 0,
      veto: true,
      tailRiskScore: 9.2,
      varEstimate5pct: 0.08,
    };
    render(<StructuredRiskCallout riskAssessment={payload} language="en" />);
    const sev = screen.getByTestId('structured-risk-severity');
    expect(sev.textContent).toContain('hard');
    expect(sev.textContent).toContain('veto=true');
    // English heading
    expect(screen.getByText(/Risk Assessment/)).toBeInTheDocument();
    // Position 0% rendered
    expect(screen.getByTestId('structured-risk-position').textContent).toBe('0.0%');
  });

  it('omits optional metric rows when their values are null/undefined', () => {
    const payload: StructuredRiskAssessment = {
      severity: 'none',
      suggestedPositionPct: 0.25,
      tailRiskScore: null,
      varEstimate5pct: null,
      volatilityAnnualised: null,
    };
    render(<StructuredRiskCallout riskAssessment={payload} language="zh" />);
    expect(screen.getByTestId('structured-risk-position').textContent).toBe('25.0%');
    expect(screen.queryByTestId('structured-risk-tail')).toBeNull();
    expect(screen.queryByTestId('structured-risk-var')).toBeNull();
    expect(screen.queryByTestId('structured-risk-vol')).toBeNull();
  });
});
