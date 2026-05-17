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
  /** Container height; defaults to 520px so the smallest holdings still have
   *  room for a one-line ticker label without being clipped at the bottom of
   *  the parent scroll region. */
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

/**
 * Colour scale for a position's unrealized PnL %. Designed to read well on a
 * light card background and to feel like a financial dashboard (Bloomberg /
 * TradingView) rather than a candy-coloured saturated palette.
 *
 * Tuning notes:
 *   - The previous version went all the way to pure rgb(240, 14, 32) red and
 *     rgb(0, 240, 36) green, which clashed badly with the cream/off-white
 *     surface and was the user's reported "刺眼" complaint.
 *   - Saturation is capped at ~55%, lightness at ~42% so blocks read as muted
 *     forest-green and brick-red instead of traffic-light primaries.
 *   - The visual cap of "extreme" is now ±15% (the practical max for a
 *     stock-level unrealized PnL on day 1 of a position). Anything beyond is
 *     clamped to the same extreme.
 */
function colourForPnlPct(pct: number | null): string {
  if (pct == null || Number.isNaN(pct)) return '#7a7e8a';

  const CAP = 15;
  const clamped = Math.max(-CAP, Math.min(CAP, pct));
  const t = Math.abs(clamped) / CAP;          // 0 at flat → 1 at extreme

  // HSL interpolation: flat = warm slate (218°, 6%, 55%);
  // gain ramps toward forest green (148°, 55%, 38%);
  // loss ramps toward muted brick (358°, 52%, 47%).
  const flat = { h: 218, s: 6, l: 55 };
  const gainEnd = { h: 148, s: 55, l: 38 };
  const lossEnd = { h: 358, s: 52, l: 47 };
  const target = clamped >= 0 ? gainEnd : lossEnd;
  const h = flat.h + (target.h - flat.h) * t;
  const s = flat.s + (target.s - flat.s) * t;
  const l = flat.l + (target.l - flat.l) * t;
  return `hsl(${h.toFixed(0)}, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
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
  // Tier thresholds: tiniest blocks just show the ticker on one line; medium
  // blocks add the percentage; large blocks get a roomier two-line layout.
  // Without the symbol-only tier, the right-edge "NET" sliver in the user's
  // screenshot rendered with no label at all.
  const showSymbol = width > 26 && height > 18;
  const showPct = width > 56 && height > 40;
  const isLarge = width > 90 && height > 70;
  const symbolSize = isLarge ? 18 : Math.max(10, Math.min(15, Math.min(width, height) / 5));
  const pctSize = isLarge ? 13 : Math.max(9, Math.min(12, Math.min(width, height) / 7));

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill,
          stroke: 'rgba(255,255,255,0.18)',
          strokeWidth: 1,
          cursor: 'pointer',
        }}
      />
      {showSymbol && name ? (
        <text
          x={x + width / 2}
          y={y + height / 2 - (showPct ? Math.round(pctSize * 0.6) : 0)}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={symbolSize}
          fontWeight={600}
          fill="rgba(255,255,255,0.98)"
          style={{ pointerEvents: 'none', letterSpacing: '0.02em' }}
        >
          {name}
        </text>
      ) : null}
      {showPct ? (
        <text
          x={x + width / 2}
          y={y + height / 2 + Math.round(symbolSize * 0.85)}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={pctSize}
          fill="rgba(255,255,255,0.88)"
          style={{ pointerEvents: 'none', fontVariantNumeric: 'tabular-nums' }}
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
  height = 520,
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
