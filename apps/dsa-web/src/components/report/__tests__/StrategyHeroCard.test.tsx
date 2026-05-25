import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StrategyHeroCard } from '../StrategyHeroCard';
import type { FactBundle, StrategyChoice } from '../../../types/analysis';

const bundle: FactBundle = {
  as_of: '2026-05-25T00:00:00Z',
  market: 'us',
  stock_code: 'NVDA',
  facts: [
    { id: 'technical.ma20', type: 'technical', label: 'MA20', value: 213.4, display_value: '$213.40' },
    { id: 'committee.pm_verdict', type: 'committee', label: 'PM 裁决', value: 'hold', display_value: 'hold (5.8/10)' },
  ],
  candidates: [],
};

const choices: StrategyChoice[] = [
  { id: 'swing_trade', labelZh: '短线波段', emoji: '⚡', applicable: true,
    fitCondition: 'RSI 超买，等回踩 MA10', timeHorizon: '1-2 周' },
  { id: 'stepped_profit_taking', labelZh: '阶梯式止盈', emoji: '🪜', applicable: true,
    fitCondition: '已有浮盈，分批了结' },
  { id: 'long_term_hold', labelZh: '长线持有', emoji: '🌳', applicable: false,
    inapplicableReason: '估值已脱离基本面' },
];

describe('StrategyHeroCard', () => {
  it('renders nothing when no choices and no thesis', () => {
    const { container } = render(<StrategyHeroCard choices={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('highlights the recommended strategy as the hero and renders its thesis text', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        thesis="RSI 71.1 超买，等回踩 MA10 再进。"
      />,
    );
    expect(screen.getByText(/AI 推荐策略：⚡ 短线波段/)).toBeInTheDocument();
    expect(screen.getByText(/RSI 71.1 超买，等回踩 MA10 再进。/)).toBeInTheDocument();
  });

  it('renders citation pills for structured thesis evidenceRefs', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        bundle={bundle}
        thesis={{
          text: '配合 PM 中性观点。',
          evidenceRefs: ['technical.ma20', 'committee.pm_verdict'],
          provenance: 'llm',
        }}
      />,
    );
    expect(screen.getByText('MA20')).toBeInTheDocument();
    expect(screen.getByText('PM 裁决')).toBeInTheDocument();
  });

  it('shows alternatives below the hero with smaller styling', () => {
    render(<StrategyHeroCard choices={choices} recommendedId="swing_trade" />);
    expect(screen.getByText(/其他候选策略/)).toBeInTheDocument();
    expect(screen.getByText('🪜 阶梯式止盈')).toBeInTheDocument();
  });

  it('lists inapplicable strategies at the bottom with reasons', () => {
    render(<StrategyHeroCard choices={choices} recommendedId="swing_trade" />);
    expect(screen.getByText(/不适用/)).toBeInTheDocument();
    expect(screen.getByText(/估值已脱离基本面/)).toBeInTheDocument();
  });

  it('renders 🤖 provenance badge when structured thesis is synthesized', () => {
    render(
      <StrategyHeroCard
        choices={choices}
        recommendedId="swing_trade"
        thesis={{ text: 't', evidenceRefs: [], provenance: 'synthesized' }}
      />,
    );
    expect(screen.getByText(/代码兜底/)).toBeInTheDocument();
  });
});
