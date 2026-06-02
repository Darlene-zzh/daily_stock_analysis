import { useState } from 'react';
import clsx from 'clsx';
import { RiRefreshLine } from '@remixicon/react';
import { stocksApi } from '../../api/stocks';

export interface RefreshPriceButtonProps {
  stockCode: string;
  onQuote: (quote: { price: number; asOf: string }) => void;
  onError?: (err: unknown) => void;
  className?: string;
}

export function RefreshPriceButton({
  stockCode,
  onQuote,
  onError,
  className,
}: RefreshPriceButtonProps) {
  const [loading, setLoading] = useState(false);

  if (!stockCode) return null;

  const handleClick = async () => {
    setLoading(true);
    try {
      const q = await stocksApi.getQuote(stockCode);
      onQuote({ price: q.currentPrice, asOf: q.asOf });
    } catch (err) {
      onError?.(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      className={clsx(
        'inline-flex items-center gap-1 rounded border px-2 py-1 text-xs',
        'border-border bg-card hover:bg-hover',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className,
      )}
      aria-label="刷新当前价"
    >
      <RiRefreshLine size={14} className={clsx(loading && 'animate-spin')} />
      <span>{loading ? '刷新中…' : '刷新价格'}</span>
    </button>
  );
}
