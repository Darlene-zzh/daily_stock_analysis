import React from 'react';
import type { SentimentDimensions } from '../../types/analysis';

interface SentimentPanelProps {
  dimensions: SentimentDimensions;
}

interface Row {
  icon: string;
  label: string;
  buzz?: number | string;
  sentiment?: number | string;
  trend?: string;
  mentions?: number | string;
}

export const SentimentPanel: React.FC<SentimentPanelProps> = ({ dimensions }) => {
  if (!dimensions || Object.keys(dimensions).length === 0) return null;

  const rows: Row[] = [];
  if (dimensions.news) {
    rows.push({
      icon: '📰', label: 'News',
      buzz: dimensions.news.buzzScore,
      sentiment: dimensions.news.sentimentScore,
      trend: dimensions.news.buzzTrend,
      mentions: dimensions.news.mentions7d,
    });
  }
  if (dimensions.reddit) {
    rows.push({
      icon: '🔴', label: 'Reddit',
      buzz: dimensions.reddit.buzzScore,
      sentiment: dimensions.reddit.sentimentScore,
      trend: dimensions.reddit.buzzTrend,
      mentions: dimensions.reddit.mentions7d,
    });
  }
  if (dimensions.xTwitter) {
    rows.push({
      icon: '🐦', label: 'X',
      buzz: dimensions.xTwitter.buzzScore,
      sentiment: dimensions.xTwitter.sentimentScore,
      trend: dimensions.xTwitter.buzzTrend,
      mentions: dimensions.xTwitter.mentions7d,
    });
  }
  if (dimensions.polymarket) {
    rows.push({
      icon: '🔮', label: 'Polymarket',
      buzz: dimensions.polymarket.buzzScore,
      sentiment: dimensions.polymarket.sentimentScore,
      mentions: dimensions.polymarket.tradeCount,
    });
  }
  if (dimensions.stocktwits) {
    const bull = dimensions.stocktwits.bullishRatio;
    const bear = dimensions.stocktwits.bearishRatio;
    rows.push({
      icon: '💬', label: 'StockTwits',
      sentiment: bull != null && bear != null
        ? `Bull ${Math.round(bull * 100)}% / Bear ${Math.round(bear * 100)}%`
        : '—',
      mentions: dimensions.stocktwits.messagesSampled,
    });
  }

  if (rows.length === 0) return null;

  return (
    <div className="rounded-xl border border-subtle bg-card p-4 space-y-2">
      <h3 className="text-sm font-semibold text-foreground">📱 市场情绪</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted-text">
            <tr>
              <th className="text-left py-1">来源</th>
              <th className="text-right py-1">Buzz</th>
              <th className="text-right py-1">Sentiment</th>
              <th className="text-right py-1">Trend</th>
              <th className="text-right py-1">Mentions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-subtle/40">
                <td className="py-1.5">{r.icon} {r.label}</td>
                <td className="text-right">{r.buzz ?? '—'}</td>
                <td className="text-right">{r.sentiment ?? '—'}</td>
                <td className="text-right text-muted-text">{r.trend ?? '—'}</td>
                <td className="text-right">{r.mentions ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
