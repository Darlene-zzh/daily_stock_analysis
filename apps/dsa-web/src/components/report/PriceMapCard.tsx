import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { RefreshPriceButton } from './RefreshPriceButton';

export type PriceMapColor = 'red' | 'green' | 'orange' | 'blue' | 'gray';
export type PriceMapRole = 'support' | 'resistance' | 'stop' | 'target' | 'ma';

export interface PriceMapLevel {
  factId: string;
  price: number;
  label: string;
  color: PriceMapColor;
  role: PriceMapRole;
}

export interface PriceMapCardProps {
  stockCode: string;
  currentPrice: number;
  currentPriceAsOf: string;
  levels: PriceMapLevel[];
  /** Optional override; when omitted, the card calls stocksApi.getQuote via the embedded RefreshPriceButton. */
  onRefresh?: () => Promise<{ price: number; asOf: string }>;
  className?: string;
}

const COLOR_TO_CLASS: Record<PriceMapColor, string> = {
  red: 'bg-danger text-danger border-danger/40',
  green: 'bg-success text-success border-success/40',
  orange: 'bg-warning text-warning border-warning/40',
  blue: 'bg-accent-brand text-accent-brand border-accent-brand/40',
  gray: 'bg-muted text-muted-text border-border',
};

function distancePct(level: number, current: number): number {
  if (current <= 0) return 0;
  return ((level - current) / current) * 100;
}

function formatPct(pct: number): string {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

export function PriceMapCard({
  stockCode,
  currentPrice,
  currentPriceAsOf,
  levels,
  onRefresh,
  className,
}: PriceMapCardProps) {
  const [displayPrice, setDisplayPrice] = useState(currentPrice);
  const [displayAsOf, setDisplayAsOf] = useState(currentPriceAsOf);

  const sortedLevels = useMemo(
    () => [...levels].sort((a, b) => a.price - b.price),
    [levels],
  );

  // Axis is pinned to the ORIGINAL currentPrice + levels. We deliberately do
  // NOT include `displayPrice` so that the user clicking 刷新价格 only slides
  // the black current-price dot; every level marker stays put. Without this
  // pinning, a 0.1% price tick reprojects every marker and the chart appears
  // to jitter unpredictably. Computed before the early return so the hook
  // order stays stable across renders (react-hooks/rules-of-hooks).
  const allPrices = useMemo(
    () => [currentPrice, ...sortedLevels.map((l) => l.price)],
    [currentPrice, sortedLevels],
  );

  if (currentPrice <= 0 || levels.length === 0) return null;

  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const padding = (maxP - minP) * 0.05 || maxP * 0.01;
  const axisMin = minP - padding;
  const axisMax = maxP + padding;
  const project = (p: number) =>
    ((p - axisMin) / (axisMax - axisMin)) * 100;

  const handleQuote = (q: { price: number; asOf: string }) => {
    setDisplayPrice(q.price);
    setDisplayAsOf(q.asOf);
  };

  // When the caller supplies onRefresh, wrap it so the card's state still updates.
  const refreshButton = onRefresh ? (
    <button
      type="button"
      onClick={async () => {
        const q = await onRefresh();
        handleQuote(q);
      }}
      className="inline-flex items-center gap-1 rounded border border-border bg-card px-2 py-1 text-xs hover:bg-hover"
      aria-label="刷新当前价"
    >
      <span>刷新价格</span>
    </button>
  ) : (
    <RefreshPriceButton stockCode={stockCode} onQuote={handleQuote} />
  );

  return (
    <div
      className={clsx(
        'rounded-lg border border-border',
        'bg-card p-4',
        className,
      )}
      data-component="price-map-card"
    >
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-xs text-secondary-text">当前价</div>
          <div className="text-2xl font-semibold tabular-nums">
            {displayPrice.toFixed(2)}
          </div>
          <div className="text-xs text-muted-text">{displayAsOf}</div>
        </div>
        {refreshButton}
      </div>

      <div className="relative h-12 mt-6">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {/* Current-price marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-foreground ring-2 ring-card"
          style={{ left: `${project(displayPrice)}%` }}
          aria-label={`当前价 ${displayPrice.toFixed(2)}`}
        />
        {/* Level markers */}
        {sortedLevels.map((lvl, idx) => {
          const pct = distancePct(lvl.price, displayPrice);
          // Alternate label position above/below to reduce overlap
          const labelAbove = idx % 2 === 0;
          return (
            <div
              key={lvl.factId}
              className="absolute top-1/2"
              style={{ left: `${project(lvl.price)}%` }}
            >
              <div
                className={clsx(
                  'absolute -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full',
                  COLOR_TO_CLASS[lvl.color].split(' ')[0],
                )}
              />
              <div
                className={clsx(
                  'absolute -translate-x-1/2 whitespace-nowrap text-xs leading-tight',
                  labelAbove ? 'bottom-4' : 'top-4',
                )}
              >
                <div className={clsx('font-medium', COLOR_TO_CLASS[lvl.color].split(' ')[1])}>
                  {lvl.label}
                </div>
                <div className="text-muted-text tabular-nums">
                  {lvl.price.toFixed(2)} · {formatPct(pct)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
