import apiClient from './index';
import { toCamelCase } from './utils';

/** One journal entry plus computed alpha. Shape mirrors the FastAPI payload
 * (snake_case) — ``toCamelCase`` does the conversion at the boundary so the
 * rest of the React app keeps speaking camelCase. */
export interface DecisionJournalEntry {
  decisionAt: string;
  priceAtDecision: number | null;
  reportLanguage: string | null;
  verdict: string | null;
  score: number | null;
  oneSentence: string | null;
  committeePmVerdict: string | null;
  keyCatalysts: string[];
  keyRisks: string[];
  analysisQueryId: string | null;
  rawReturn: number | null;
  benchmarkReturn: number | null;
  alpha: number | null;
}

export interface DecisionJournalResponse {
  stockCode: string;
  market: string;
  count: number;
  entries: DecisionJournalEntry[];
}

export const decisionJournalApi = {
  /** Fetch the journal entries for ``stockCode``.
   *
   * ``market`` is optional — backend infers from the code shape.
   * ``limit`` defaults to 20 (matches the Web tab listing size). */
  list: async (
    stockCode: string,
    options: { market?: string; limit?: number } = {},
  ): Promise<DecisionJournalResponse> => {
    const params: Record<string, string | number> = {};
    if (options.market) params.market = options.market;
    if (options.limit !== undefined) params.limit = options.limit;
    const response = await apiClient.get(
      `/api/v1/decision-journal/${encodeURIComponent(stockCode)}`,
      { params },
    );
    return toCamelCase(response.data) as DecisionJournalResponse;
  },
};
