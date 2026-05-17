import type React from 'react';
import type { ReportLanguage, ReportStrategy as ReportStrategyType } from '../../types/analysis';
import { Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportStrategyProps {
  strategy?: ReportStrategyType;
  language?: ReportLanguage;
  /**
   * When the AI-recommended strategy is "wait_and_see", showing the sniper
   * entry/exit prices in bold contradicts the advisory. Pass the recommended
   * strategy id and the card mutes itself with a reference-only notice.
   */
  recommendedStrategy?: string;
}

interface StrategyItemProps {
  label: string;
  value?: string;
  tone: string;
  muted?: boolean;
}

const StrategyItem: React.FC<StrategyItemProps> = ({
  label,
  value,
  tone,
  muted = false,
}) => (
  <div className="home-subpanel home-strategy-card p-3" style={{ ['--home-strategy-tone' as string]: `var(${tone})`, opacity: muted ? 0.55 : undefined }}>
    <div className="flex flex-col">
      <span className="home-strategy-label mb-0.5 text-xs">{label}</span>
      <span className="home-strategy-value text-lg font-bold font-mono" style={!value ? { color: 'var(--text-muted-text)' } : undefined}>
        {value || '—'}
      </span>
    </div>
    <div
      className="absolute bottom-0 left-0 right-0 h-0.5"
      style={{ background: `linear-gradient(90deg, transparent, var(${tone}), transparent)` }}
    />
  </div>
);

/**
 * 策略点位区组件 - 终端风格
 */
export const ReportStrategy: React.FC<ReportStrategyProps> = ({ strategy, language = 'zh', recommendedStrategy }) => {
  if (!strategy) {
    return null;
  }

  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const isWaitAndSee = recommendedStrategy === 'wait_and_see';

  const strategyItems = [
    {
      label: text.idealBuy,
      value: strategy.idealBuy,
      tone: '--home-strategy-buy',
    },
    {
      label: text.secondaryBuy,
      value: strategy.secondaryBuy,
      tone: '--home-strategy-secondary',
    },
    {
      label: text.stopLoss,
      value: strategy.stopLoss,
      tone: '--home-strategy-stop',
    },
    {
      label: text.takeProfit,
      value: strategy.takeProfit,
      tone: '--home-strategy-take',
    },
  ];

  return (
    <Card variant="bordered" padding="md" className="home-panel-card">
      <DashboardPanelHeader
        eyebrow={text.strategyPoints}
        title={text.sniperLevels}
        className="mb-3"
      />
      {isWaitAndSee && (
        <p className="mb-3 text-xs text-muted-text leading-relaxed">
          {text.strategyPointsWaitNotice}
        </p>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {strategyItems.map((item) => (
          <StrategyItem key={item.label} {...item} muted={isWaitAndSee} />
        ))}
      </div>
    </Card>
  );
};
