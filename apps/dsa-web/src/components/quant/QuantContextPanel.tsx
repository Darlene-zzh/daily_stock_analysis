import { useEffect, useState } from 'react';

import {
  quantSignalApi,
  type QuantSignalResponse,
} from '../../api/quantSignal';
import type { ReportLanguage } from '../../types/analysis';

/**
 * Sprint 3 — Quant Context panel.
 *
 * Renders a compact factor strip + (optional) forecast banner with an
 * "Auxiliary signal" disclaimer at the top.  Per locked decisions:
 *
 *  - Renders nothing at all when the backend returns 204 (no qlib data
 *    or stock outside CSI 300 / S&P 500 universe).
 *  - Shows factors only with an "uncertain" tag when the model IC is
 *    below the gate threshold (forecast suppressed by the API).
 *  - Always carries the "auxiliary, not a recommendation" caveat.
 */

interface QuantContextPanelProps {
  stockCode: string;
  /** Optional market hint; backend infers when omitted. */
  market?: string;
  /** Forecast horizon override; defaults to the backend's value. */
  horizon?: number;
  /** Drives Chinese/English copy. */
  language?: ReportLanguage;
  /** Test seam — when provided, the panel skips its own fetch. */
  initialData?: QuantSignalResponse | null;
  /** Optional dependency-injection for the API client (used in tests). */
  api?: typeof quantSignalApi;
}

const text = (language: ReportLanguage) => {
  const en = language === 'en';
  return {
    title: en ? 'Quant Context (auxiliary)' : '量化辅助信号 (Quant Context)',
    caveat: en
      ? 'Auxiliary statistical signal — NOT a buy/sell recommendation. The model only reads historical price-volume factors; weight well below fundamentals and news.'
      : '辅助统计信号，**非买卖建议**。模型仅基于历史价量因子，权重应明显低于基本面 / 技术面 / 情绪面。',
    factorsHeading: en ? 'Factor snapshot' : '因子快照',
    forecastHeading: en ? 'Forecast' : '模型预测',
    horizon: en ? 'Horizon' : '预测期',
    days: en ? 'trading days' : '个交易日',
    score: en ? 'Raw score' : '原始分',
    rank: en ? 'Universe rank' : '池内分位',
    icCurrent: en ? 'Current Rank IC' : '当期 Rank IC',
    icMa: en ? '4-week IC MA' : '4 周 IC 均线',
    version: en ? 'Model version' : '模型版本',
    uncertain: en
      ? 'Model currently uncertain (IC below gate or no artifact); showing factors only, no forecast.'
      : '当前模型不稳定（IC 低于门限或暂无权重）— 仅展示因子，未给出预测。',
    loading: en ? 'Loading quant context...' : '正在加载量化辅助信号...',
  };
};

const formatNumber = (value: number | null | undefined, digits = 4): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}`;
};

const formatPercent = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(2)}%`;
};

const factorBarStyle = (value: number): React.CSSProperties => {
  // Map -1..+1 to 0..100 % width; clamp larger absolute values to the edges.
  const clamped = Math.max(-1, Math.min(1, value));
  const width = Math.abs(clamped) * 50; // 0..50% half-width
  const color = clamped >= 0 ? 'rgb(16 185 129)' : 'rgb(244 63 94)'; // emerald / rose
  return {
    width: `${width}%`,
    backgroundColor: color,
    height: '6px',
    borderRadius: '3px',
    marginLeft: clamped >= 0 ? '50%' : `${50 - width}%`,
  };
};

export const QuantContextPanel: React.FC<QuantContextPanelProps> = ({
  stockCode,
  market,
  horizon,
  language = 'zh',
  initialData,
  api = quantSignalApi,
}) => {
  const labels = text(language);
  // Test seam: when ``initialData`` is supplied (including null), the
  // panel skips its own fetch entirely and just renders that value.
  // We track only the *fetched* state here, so the React Compiler-style
  // lint rule against synchronous setState in effects stays happy.
  const useInitial = initialData !== undefined;
  const [fetched, setFetched] = useState<QuantSignalResponse | null | undefined>(undefined);

  useEffect(() => {
    if (useInitial) {
      return;
    }
    let cancelled = false;
    (async () => {
      const result = await api.fetch(stockCode, { market, horizon });
      if (!cancelled) setFetched(result);
    })();
    return () => {
      cancelled = true;
    };
  }, [stockCode, market, horizon, useInitial, api]);

  const data = useInitial ? initialData : fetched;

  // Loading state — only shows the first time; subsequent renders with
  // ``null`` (no signal) just render nothing.
  if (data === undefined) {
    return (
      <div
        className="rounded-xl border border-dashed border-subtle px-4 py-3 text-xs text-muted-text"
        data-testid="quant-context-loading"
      >
        {labels.loading}
      </div>
    );
  }

  if (data === null) {
    // No signal available — silent no-op (Q6 locked decision).
    return null;
  }

  const { factors, forecast } = data;
  if (!factors && !forecast) return null;

  return (
    <section
      className="rounded-xl border border-subtle bg-card p-4 space-y-3"
      data-testid="quant-context-panel"
      aria-label={labels.title}
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight">{labels.title}</h3>
        <span className="text-[10px] uppercase tracking-wider text-muted-text">
          auxiliary
        </span>
      </header>

      <p
        className="text-xs text-muted-text leading-snug"
        data-testid="quant-context-caveat"
      >
        {labels.caveat}
      </p>

      {factors && Object.keys(factors.quantiles).length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-text">
            {labels.factorsHeading}
          </div>
          <ul className="space-y-1.5">
            {Object.entries(factors.quantiles).map(([name, value]) => (
              <li
                key={name}
                className="grid grid-cols-[8rem_3rem_1fr] items-center gap-2 text-xs"
                data-testid={`quant-factor-${name}`}
              >
                <code className="text-[11px] text-muted-text truncate">{name}</code>
                <span className="text-right tabular-nums">
                  {formatNumber(value)}
                </span>
                <div className="bg-subtle/30 rounded h-1.5 relative">
                  <div style={factorBarStyle(value)} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {forecast ? (
        <div className="space-y-1 text-xs">
          <div className="font-medium text-muted-text">{labels.forecastHeading}</div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
            <dt className="text-muted-text">{labels.horizon}</dt>
            <dd className="tabular-nums">
              {forecast.horizonDays} {labels.days}
            </dd>
            <dt className="text-muted-text">{labels.score}</dt>
            <dd className="tabular-nums">
              {formatNumber(forecast.expectedExcessReturn)}
            </dd>
            {forecast.rankInUniverse !== null && (
              <>
                <dt className="text-muted-text">{labels.rank}</dt>
                <dd className="tabular-nums">{formatPercent(forecast.rankInUniverse)}</dd>
              </>
            )}
            {forecast.icCurrent !== null && (
              <>
                <dt className="text-muted-text">{labels.icCurrent}</dt>
                <dd className="tabular-nums">{formatNumber(forecast.icCurrent)}</dd>
              </>
            )}
            {forecast.icMa4w !== null && (
              <>
                <dt className="text-muted-text">{labels.icMa}</dt>
                <dd className="tabular-nums">{formatNumber(forecast.icMa4w)}</dd>
              </>
            )}
            {forecast.modelVersion && (
              <>
                <dt className="text-muted-text">{labels.version}</dt>
                <dd className="font-mono text-[11px]">{forecast.modelVersion}</dd>
              </>
            )}
          </dl>
        </div>
      ) : (
        factors && (
          <div
            className="text-xs text-amber-700 dark:text-amber-300"
            data-testid="quant-context-uncertain"
          >
            ⚠️ {labels.uncertain}
          </div>
        )
      )}
    </section>
  );
};

export default QuantContextPanel;
