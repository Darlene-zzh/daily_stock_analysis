import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  Treemap,
  Tooltip,
} from 'recharts';
import { portfolioApi } from '../../api/portfolio';
import { getParsedApiError } from '../../api/error';
import { Card, EmptyState } from '../common';
import type { PortfolioPositionItem } from '../../types/portfolio';

/**
 * Portfolio heatmap rendered as a treemap.
 *
 * Block size: market_value_base (so bigger positions dominate the canvas).
 * Block color: gradient from red (unrealized loss) → grey (flat) → green
 *   (unrealized gain). We use the position's unrealized PnL percentage as
 *   the colour signal — the daily change is not in the position payload
 *   today and pulling it would require an extra realtime quote per holding.
 *
 * Click a block → fire the caller-supplied `onSelectSymbol` so the parent
 * can wire it to "analyze this stock" or any other action.
 */
export interface PortfolioHeatmapTreemapProps {
  /** Optional account filter; when omitted the snapshot aggregates all accounts. */
  accountId?: number;
  /** Click handler when a block is selected. */
  onSelectSymbol?: (symbol: string) => void;
  /** Container height; defaults to 420px which fits the home-page empty slot. */
  height?: number;
  /** Override the snapshot data instead of fetching (useful for tests + storybook). */
  positionsOverride?: PortfolioPositionItem[];
}

type TreemapDatum = {
  name: string;
  size: number;
  pnlPct: number | null;
  pnlBase: number;
  qty: number;
  lastPrice: number;
  avgCost: number;
};

/** Colour scale: red at -10%+, grey at flat, green at +10%+. Linear in between. */
function colourForPnlPct(pct: number | null): string {
  if (pct == null || Number.isNaN(pct)) return 'var(--color-surface-muted, #2a2f3a)';
  const clamped = Math.max(-10, Math.min(10, pct));
  if (clamped >= 0) {
    // 0 → grey-green, 10 → vivid green
    const intensity = clamped / 10;
    const r = Math.round(64 - 64 * intensity);
    const g = Math.round(140 + 100 * intensity);
    const b = Math.round(96 - 60 * intensity);
    return `rgb(${r},${g},${b})`;
  }
  // -10 → vivid red, 0 → grey-red
  const intensity = -clamped / 10;
  const r = Math.round(140 + 100 * intensity);
  const g = Math.round(64 - 50 * intensity);
  const b = Math.round(72 - 40 * intensity);
  return `rgb(${r},${g},${b})`;
}

function formatPct(pct: number | null): string {
  if (pct == null || Number.isNaN(pct)) return '--';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function formatMoney(value: number, currency: string): string {
  return `${currency} ${value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

interface TreemapContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  size?: number;
  pnlPct?: number | null;
}

function TreemapBlock({ x = 0, y = 0, width = 0, height = 0, name, pnlPct }: TreemapContentProps) {
  const fill = colourForPnlPct(pnlPct ?? null);
  // Only render label when block is big enough to fit ~3 chars + percentage.
  const showLabel = width > 48 && height > 36;
  const showPct = width > 60 && height > 54;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill,
          stroke: 'rgba(0,0,0,0.35)',
          strokeWidth: 1,
          cursor: 'pointer',
        }}
      />
      {showLabel && name ? (
        <text
          x={x + width / 2}
          y={y + height / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={Math.min(16, Math.max(11, Math.min(width, height) / 5))}
          fontWeight={600}
          fill="rgba(255,255,255,0.96)"
        >
          {name}
        </text>
      ) : null}
      {showPct ? (
        <text
          x={x + width / 2}
          y={y + height / 2 + 16}
          textAnchor="middle"
          fontSize={Math.min(13, Math.max(10, Math.min(width, height) / 7))}
          fill="rgba(255,255,255,0.86)"
        >
          {formatPct(pnlPct ?? null)}
        </text>
      ) : null}
    </g>
  );
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload?: TreemapDatum & { currency?: string } }>;
}

function HeatmapTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0]?.payload;
  if (!data) return null;
  const currency = data.currency || '';
  return (
    <div className="rounded-lg border border-subtle bg-card/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-semibold text-foreground">{data.name}</div>
      <div className="mt-1 text-muted-text">
        持仓 {data.qty} 股 @ 成本 {data.avgCost.toFixed(2)}
      </div>
      <div className="text-muted-text">
        现价 {data.lastPrice.toFixed(2)}
      </div>
      <div className={`mt-1 font-medium ${(data.pnlPct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        {formatPct(data.pnlPct)} · {formatMoney(data.pnlBase, currency)}
      </div>
    </div>
  );
}

export const PortfolioHeatmapTreemap: React.FC<PortfolioHeatmapTreemapProps> = ({
  accountId,
  onSelectSymbol,
  height = 420,
  positionsOverride,
}) => {
  const [positions, setPositions] = useState<PortfolioPositionItem[]>(positionsOverride ?? []);
  const [isLoading, setIsLoading] = useState(!positionsOverride);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [baseCurrency, setBaseCurrency] = useState<string>('GBP');

  useEffect(() => {
    if (positionsOverride) {
      setPositions(positionsOverride);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    void (async () => {
      try {
        const snap = await portfolioApi.getSnapshot({ accountId });
        if (cancelled) return;
        const flattened: PortfolioPositionItem[] = [];
        let resolvedCurrency: string | undefined;
        for (const acc of snap.accounts ?? []) {
          for (const p of acc.positions ?? []) {
            flattened.push(p);
          }
          if (!resolvedCurrency && acc.baseCurrency) resolvedCurrency = acc.baseCurrency;
        }
        setPositions(flattened);
        if (resolvedCurrency) setBaseCurrency(resolvedCurrency);
      } catch (err) {
        if (cancelled) return;
        setErrorMsg(getParsedApiError(err).message);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId, positionsOverride]);

  const data = useMemo<Array<TreemapDatum & { currency: string }>>(() => {
    return positions
      .filter((p) => p.marketValueBase > 0)
      .map((p) => ({
        name: p.symbol,
        size: p.marketValueBase,
        pnlPct: p.unrealizedPnlPct ?? null,
        pnlBase: p.unrealizedPnlBase,
        qty: p.quantity,
        lastPrice: p.lastPrice,
        avgCost: p.avgCost,
        currency: baseCurrency,
      }))
      .sort((a, b) => b.size - a.size);
  }, [positions, baseCurrency]);

  if (isLoading) {
    return (
      <Card variant="bordered" padding="md" className="home-panel-card">
        <div className="flex h-[200px] items-center justify-center text-sm text-muted-text">
          正在加载持仓热点图…
        </div>
      </Card>
    );
  }

  if (errorMsg) {
    return (
      <Card variant="bordered" padding="md" className="home-panel-card">
        <div className="text-sm text-red-400">持仓数据加载失败：{errorMsg}</div>
      </Card>
    );
  }

  if (!data.length) {
    return (
      <EmptyState
        title="还没有持仓数据"
        description="导入交易记录或同步券商后，这里会显示你的持仓热点图。"
        className="max-w-xl border-dashed"
      />
    );
  }

  return (
    <Card variant="bordered" padding="md" className="home-panel-card">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-foreground">📊 持仓热点图</h3>
        <span className="text-xs text-muted-text">
          色块大小 = 仓位市值 · 颜色 = 浮盈百分比 · 点击进入分析
        </span>
      </div>
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer>
          <Treemap
            data={data}
            dataKey="size"
            nameKey="name"
            isAnimationActive={false}
            content={<TreemapBlock />}
            onClick={(node: unknown) => {
              if (!onSelectSymbol) return;
              const datum = (node as { name?: string } | undefined);
              if (datum?.name) onSelectSymbol(datum.name);
            }}
          >
            <Tooltip content={<HeatmapTooltip />} />
          </Treemap>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};
