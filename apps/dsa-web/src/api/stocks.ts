import apiClient from './index';

export type ExtractItem = {
  code?: string | null;
  name?: string | null;
  confidence: string;
};

export type ExtractFromImageResponse = {
  codes: string[];
  items?: ExtractItem[];
  rawText?: string;
};

export type QuoteResponse = {
  stockCode: string;
  stockName: string | null;
  currentPrice: number;
  changePercent: number | null;
  asOf: string; // ISO timestamp
};

export const stocksApi = {
  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    const data = response.data as { codes?: string[]; items?: ExtractItem[]; raw_text?: string };
    return {
      codes: data.codes ?? [],
      items: data.items,
      rawText: data.raw_text,
    };
  },

  async parseImport(file?: File, text?: string): Promise<ExtractFromImageResponse> {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
      const response = await apiClient.post('/api/v1/stocks/parse-import', formData, { headers });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    if (text) {
      const response = await apiClient.post('/api/v1/stocks/parse-import', { text });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    throw new Error('请提供文件或粘贴文本');
  },

  async getQuote(stockCode: string): Promise<QuoteResponse> {
    const response = await apiClient.get(`/api/v1/stocks/${stockCode}/quote`);
    const data = response.data as {
      stock_code?: string;
      stock_name?: string | null;
      current_price?: number;
      change_percent?: number | null;
      update_time?: string;
    };
    if (typeof data.current_price !== 'number') {
      throw new Error(`getQuote(${stockCode}): missing current_price in response`);
    }
    return {
      stockCode: data.stock_code ?? stockCode,
      stockName: data.stock_name ?? null,
      currentPrice: data.current_price,
      changePercent: data.change_percent ?? null,
      asOf: data.update_time ?? new Date().toISOString(),
    };
  },
};
