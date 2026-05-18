import apiClient from './index';
import { toCamelCase } from './utils';

/**
 * Sprint 3 — Quant signal client.
 *
 * Backend contract: ``GET /api/v1/quant-signal/{code}?market=&horizon=``
 *  - 200 + payload → factor quantiles + (optional) forecast
 *  - 204 No Content → qlib data / model not available, panel renders nothing
 *
 * The panel calls this via ``QuantSignalApi.fetch`` and treats ``null``
 * the same as 204: hide the section.  Any other error also degrades to
 * ``null`` because quant context is strictly auxiliary.
 */

/** Single factor snapshot keyed by short name. */
export interface QuantFactorSnapshot {
  stockCode: string;
  market: string;
  asOf: string;
  quantiles: Record<string, number>;
}

/** Forecast banner row. */
export interface QuantForecast {
  stockCode: string;
  market: string;
  asOf: string;
  horizonDays: number;
  expectedExcessReturn: number;
  rankInUniverse: number | null;
  icCurrent: number | null;
  icMa4w: number | null;
  modelVersion: string | null;
}

export interface QuantSignalResponse {
  stockCode: string;
  market: string;
  horizonDays: number;
  factors: QuantFactorSnapshot | null;
  forecast: QuantForecast | null;
}

export const quantSignalApi = {
  /** Fetch quant context for ``stockCode``.  Returns ``null`` when the
   * backend says 204 (no signal available) or any error occurs. */
  fetch: async (
    stockCode: string,
    options: { market?: string; horizon?: number } = {},
  ): Promise<QuantSignalResponse | null> => {
    const params: Record<string, string | number> = {};
    if (options.market) params.market = options.market;
    if (options.horizon !== undefined) params.horizon = options.horizon;
    try {
      const response = await apiClient.get(
        `/api/v1/quant-signal/${encodeURIComponent(stockCode)}`,
        { params, validateStatus: (status) => status < 500 },
      );
      if (response.status === 204 || !response.data) {
        return null;
      }
      return toCamelCase(response.data) as QuantSignalResponse;
    } catch {
      // Network / serialisation failure — still degrade gracefully.
      return null;
    }
  },
};
