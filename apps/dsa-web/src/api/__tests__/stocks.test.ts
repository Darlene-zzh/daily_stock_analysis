import { describe, expect, it, vi, beforeEach } from 'vitest';
import { stocksApi } from '../stocks';
import apiClient from '../index';

vi.mock('../index', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
    },
  };
});

describe('stocksApi.getQuote', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('GETs /api/v1/stocks/{code}/quote and maps to camelCase', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        stock_code: 'NVDA',
        stock_name: 'NVIDIA',
        current_price: 226.13,
        change_percent: 1.23,
        update_time: '2026-05-24T10:00:00Z',
      },
    });

    const quote = await stocksApi.getQuote('NVDA');

    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/stocks/NVDA/quote');
    expect(quote).toEqual({
      stockCode: 'NVDA',
      stockName: 'NVIDIA',
      currentPrice: 226.13,
      changePercent: 1.23,
      asOf: '2026-05-24T10:00:00Z',
    });
  });

  it('throws when the response is missing current_price', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { stock_code: 'NVDA' },
    });
    await expect(stocksApi.getQuote('NVDA')).rejects.toThrow();
  });

  it('encodes the stock code into the URL path', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { stock_code: 'hk00700', current_price: 350.5, update_time: '2026-05-24T10:00:00Z' },
    });
    await stocksApi.getQuote('hk00700');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/stocks/hk00700/quote');
  });
});
