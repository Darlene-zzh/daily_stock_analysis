import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { portfolioApi } from '../api/portfolio';
import type {
  PortfolioPositionItem,
  PortfolioRealtimePriceItem,
} from '../types/portfolio';

export interface LivePriceState {
  /** Map of symbol → most recent realtime price record. */
  prices: Record<string, PortfolioRealtimePriceItem>;
  /** Wall-clock timestamp (browser local) of the most recent successful poll. */
  lastFetchedAt: Date | null;
  /** True while a request is in flight. */
  isFetching: boolean;
  /** Whether the next polling tick is enabled. */
  isEnabled: boolean;
  /** Trigger an immediate fetch (also called on toggle / interval). */
  refresh: () => Promise<void>;
  /** Pause / resume polling without losing already-fetched prices. */
  setEnabled: (next: boolean) => void;
}

/**
 * Polls `/api/v1/portfolio/prices/lookup` on a fixed interval and exposes the
 * most recent price per symbol. Designed to overlay a snapshot — the snapshot
 * already provides cost basis, FX, and persisted last price; this hook just
 * keeps the price column fresh between full snapshot refreshes.
 *
 * - First fetch fires immediately on mount when enabled.
 * - Subsequent fetches happen every `intervalMs` (default 60s).
 * - Toggling `enabled` to false stops the interval but keeps the last known
 *   prices visible so the page does not flash back to stale values.
 * - Empty position lists are a no-op (no fetcher calls, no timer scheduled).
 */
export function usePortfolioRealtimePrices(
  positions: PortfolioPositionItem[],
  options: { intervalMs?: number; initiallyEnabled?: boolean } = {},
): LivePriceState {
  const intervalMs = options.intervalMs ?? 60_000;
  const [isEnabled, setEnabled] = useState<boolean>(options.initiallyEnabled ?? true);
  const [prices, setPrices] = useState<Record<string, PortfolioRealtimePriceItem>>({});
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [isFetching, setFetching] = useState(false);

  // Stable signature for the position set so we re-fetch only when the
  // underlying symbol/currency tuples actually change.
  const positionsSignature = useMemo(() => {
    return positions
      .map((p) => `${p.symbol}::${p.currency ?? ''}`)
      .sort()
      .join('|');
  }, [positions]);

  const lookupPayload = useMemo(() => {
    return positions.map((p) => ({ symbol: p.symbol, currency: p.currency ?? null }));
  }, [positions]);

  const payloadRef = useRef(lookupPayload);
  payloadRef.current = lookupPayload;

  const refresh = useCallback(async () => {
    const payload = payloadRef.current;
    if (!payload.length) return;
    setFetching(true);
    try {
      const res = await portfolioApi.lookupRealtimePrices({ positions: payload });
      const next: Record<string, PortfolioRealtimePriceItem> = {};
      for (const item of res.items) {
        next[item.symbol] = item;
      }
      setPrices(next);
      setLastFetchedAt(new Date());
    } catch {
      // Silently fail polling; preserve the previous prices.
    } finally {
      setFetching(false);
    }
  }, []);

  // Reset cached prices when the underlying position set changes (e.g. the
  // user switches accounts) so we do not bleed prices across views.
  useEffect(() => {
    setPrices({});
    setLastFetchedAt(null);
  }, [positionsSignature]);

  useEffect(() => {
    if (!isEnabled) return undefined;
    if (!lookupPayload.length) return undefined;
    void refresh();
    const id = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(id);
  }, [isEnabled, intervalMs, positionsSignature, lookupPayload.length, refresh]);

  return {
    prices,
    lastFetchedAt,
    isFetching,
    isEnabled,
    refresh,
    setEnabled,
  };
}
