import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CommitteeMinutesPanel } from '../CommitteeMinutesPanel';
import type { CommitteeMinutes } from '../../../types/analysis';

const fullMinutes: CommitteeMinutes = {
  version: '1',
  status: 'ok',
  debateRounds: 2,
  debate: [
    { side: 'bull', roundIndex: 1, claim: 'Moat is widening on cloud monetisation.' },
    { side: 'bear', roundIndex: 1, claim: 'Capex is outrunning free cash flow.' },
    { side: 'bull', roundIndex: 2, claim: 'AI accelerator demand offsets capex risk.' },
    { side: 'bear', roundIndex: 2, claim: 'Customer concentration remains a red flag.' },
  ],
  masters: [
    {
      persona: 'warren_buffett',
      verdict: 'buy',
      score: 7.2,
      headline: 'Reasonable price for a durable franchise.',
      rationale: 'Wide moat, ROIC > 20%, predictable cash flow.',
      keyEvidence: ['ROIC 21%', 'Operating margin 32%'],
      counterView: 'Margin compression below 25%.',
      toolsUsed: ['fundamentals_snapshot'],
      status: 'ok',
    },
    {
      persona: 'michael_burry',
      verdict: 'avoid',
      score: 4.1,
      headline: 'Inventory build-up and aggressive accruals.',
      rationale: 'Days sales outstanding climbing for 3 quarters.',
      keyEvidence: ['DSO 78 days'],
      status: 'ok',
    },
    {
      persona: 'cathie_wood',
      verdict: 'strong_buy',
      score: 8.6,
      headline: 'Innovation curve still steep — TAM expanding.',
      rationale: 'AI inference demand 3x YoY.',
      status: 'ok',
    },
    {
      persona: 'nassim_taleb',
      verdict: 'hold',
      score: 5.0,
      headline: 'Fat-tailed regulatory exposure.',
      rationale: 'Concentration risk in single jurisdiction.',
      status: 'ok',
    },
  ],
  risk: {
    severity: 'soft',
    redFlags: ['Customer concentration > 35%'],
    suggestedPositionPct: 0.05,
    veto: false,
    status: 'ok',
  },
  pmVerdict: 'buy',
  pmScore: 6.8,
  pmRationale: 'Committee leans constructive but Burry dissent is material.',
  pmDissents: ['michael_burry'],
  budgetUsed: 12,
  budgetCap: 12,
  missingAgents: [],
  latencyMs: 18500,
};

describe('CommitteeMinutesPanel', () => {
  it('renders null when committee payload is missing (graceful)', () => {
    const { container } = render(<CommitteeMinutesPanel committee={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders PM verdict, debate timeline, all four lens cards, and risk strip on a full ok payload', () => {
    render(<CommitteeMinutesPanel committee={fullMinutes} language="zh" />);

    // Header
    expect(screen.getByText('投委会会议纪要')).toBeInTheDocument();

    // Status banner absent on ok
    expect(screen.queryByTestId('committee-status-banner')).toBeNull();

    // PM card with verdict text + score (scope to PM card — Buffett lens also renders "买入")
    const pmCard = screen.getByTestId('committee-pm-card');
    expect(pmCard).toBeInTheDocument();
    expect(within(pmCard).getByText('买入')).toBeInTheDocument();

    // All four lens cards present
    expect(screen.getByTestId('committee-lens-card-warren_buffett')).toHaveAttribute(
      'data-status',
      'present',
    );
    expect(screen.getByTestId('committee-lens-card-michael_burry')).toHaveAttribute(
      'data-status',
      'present',
    );
    expect(screen.getByTestId('committee-lens-card-cathie_wood')).toHaveAttribute(
      'data-status',
      'present',
    );
    expect(screen.getByTestId('committee-lens-card-nassim_taleb')).toHaveAttribute(
      'data-status',
      'present',
    );

    // Inspired-lens framing (verify English string from PERSONA_DISPLAY)
    expect(screen.getByText('Buffett-inspired value lens')).toBeInTheDocument();
    expect(screen.getByText('Burry-inspired contrarian lens')).toBeInTheDocument();
    expect(screen.getByText('Cathie Wood-inspired innovation lens')).toBeInTheDocument();
    expect(screen.getByText('Taleb-inspired tail-risk lens')).toBeInTheDocument();

    // Chinese parenthetical appears only on first lens card in zh mode
    expect(screen.getByText('巴菲特式价值视角')).toBeInTheDocument();
    expect(screen.queryByText('Burry 式逆向视角')).toBeNull();

    // Debate timeline shows both rounds
    expect(screen.getByTestId('committee-debate-timeline')).toBeInTheDocument();
    expect(screen.getByText('第 1 轮')).toBeInTheDocument();
    expect(screen.getByText('第 2 轮')).toBeInTheDocument();

    // Risk strip rendered with soft severity
    expect(screen.getByTestId('committee-risk-strip')).toBeInTheDocument();
    expect(screen.getByText('软风险')).toBeInTheDocument();
  });

  it('shows the amber partial banner and renders absent lens for failed master', () => {
    const partialMinutes: CommitteeMinutes = {
      ...fullMinutes,
      status: 'partial',
      missingAgents: ['nassim_taleb'],
      masters: fullMinutes.masters!.filter((m) => m.persona !== 'nassim_taleb'),
    };

    render(<CommitteeMinutesPanel committee={partialMinutes} language="en" />);

    const banner = screen.getByTestId('committee-status-banner');
    expect(banner).toHaveTextContent('1 agent absent');
    // PM card still visible on partial
    expect(screen.getByTestId('committee-pm-card')).toBeInTheDocument();
    // Taleb card greyed-out / absent
    const talebCard = screen.getByTestId('committee-lens-card-nassim_taleb');
    expect(talebCard).toHaveAttribute('data-status', 'absent');
    expect(screen.getByTestId('committee-lens-absent-nassim_taleb')).toHaveTextContent('absent');
  });

  it('suppresses the PM verdict card when status="failed"', () => {
    const failedMinutes: CommitteeMinutes = {
      ...fullMinutes,
      status: 'failed',
      pmVerdict: undefined,
      pmRationale: undefined,
    };

    render(<CommitteeMinutesPanel committee={failedMinutes} language="en" />);

    expect(screen.getByTestId('committee-status-banner')).toHaveTextContent(
      'Committee inconclusive',
    );
    expect(screen.queryByTestId('committee-pm-card')).toBeNull();
  });

  it('toggles rationale visibility when "Show rationale" is clicked', () => {
    render(<CommitteeMinutesPanel committee={fullMinutes} language="en" />);

    // Rationale is collapsed by default
    expect(screen.queryByTestId('committee-lens-rationale-warren_buffett')).toBeNull();

    // Click the Show rationale button inside the Buffett card.
    const buffettCard = screen.getByTestId('committee-lens-card-warren_buffett');
    const button = buffettCard.querySelector('button');
    expect(button).not.toBeNull();
    fireEvent.click(button!);

    expect(screen.getByTestId('committee-lens-rationale-warren_buffett')).toBeInTheDocument();
  });

  it('uses English persona display names in en-mode and omits the Chinese parenthetical', () => {
    render(<CommitteeMinutesPanel committee={fullMinutes} language="en" />);

    expect(screen.getByText('Investment Committee Minutes')).toBeInTheDocument();
    // Even though firstZhEmitted toggles, Chinese subtitle should not render in en mode.
    expect(screen.queryByText('巴菲特式价值视角')).toBeNull();
  });
});
