import { useEffect, useMemo, useState } from 'react';

import {
  decisionJournalApi,
  type DecisionJournalEntry,
} from '../../api/decisionJournal';
import type { ReportLanguage } from '../../types/analysis';

interface DecisionTrackingTabProps {
  stockCode: string;
  /** Optional market hint — backend infers from the code otherwise. */
  market?: string;
  /** Drives Chinese/English labels.  Defaults to ``zh``. */
  language?: ReportLanguage;
  /**
   * Test seam — when supplied, the component skips its own fetch and
   * renders the provided entries directly.  Keeps the unit tests free of
   * network or mock-axios plumbing.
   */
  initialEntries?: DecisionJournalEntry[];
  /** Optional dependency-injection for the API client (used in tests). */
  api?: typeof decisionJournalApi;
  /** Max entries to render (default 20). */
  limit?: number;
}

const text = (language: ReportLanguage) => {
  const en = language === 'en';
  return {
    title: en ? 'Decision Tracking' : '复盘 / Decision Tracking',
    emptyState: en
      ? 'No prior analyses on this stock yet — the journal will populate after the first run.'
      : '暂无该股的历史分析记录——首次分析后会自动写入决策日志。',
    loading: en ? 'Loading journal...' : '正在加载决策日志...',
    error: en
      ? 'Could not load the decision journal. Try refreshing.'
      : '无法加载决策日志，请稍后重试。',
    columnDate: en ? 'Date' : '日期',
    columnVerdict: en ? 'Verdict' : '观点',
    columnScore: en ? 'Score' : '评分',
    columnRaw: en ? 'Raw return' : '原始收益',
    columnAlpha: en ? 'Alpha vs benchmark' : '相对基准 Alpha',
    columnSummary: en ? 'One-sentence thesis' : '观点摘要',
    sparkline: en ? 'Alpha trend (oldest → newest)' : 'Alpha 趋势（旧 → 新）',
    alphaUnavailable: en ? 'benchmark unavailable' : '基准未取到',
  };
};

const formatPercent = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  const pct = value * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
};

const alphaToneClass = (alpha: number | null | undefined): string => {
  if (typeof alpha !== 'number') return 'text-muted-text';
  if (alpha > 0.001) return 'text-emerald-600 font-medium';
  if (alpha < -0.001) return 'text-rose-600 font-medium';
  return 'text-yellow-700';
};

interface AlphaSparklineProps {
  values: Array<number | null>;
  label: string;
}

/** Minimal inline SVG sparkline so we don't pull in a charting lib for one
 * line.  Null entries are rendered as gaps. */
const AlphaSparkline: React.FC<AlphaSparklineProps> = ({ values, label }) => {
  if (values.length === 0) return null;
  const numeric = values.filter(
    (v): v is number => typeof v === 'number' && !Number.isNaN(v),
  );
  if (numeric.length === 0) {
    return (
      <div className="text-xs text-muted-text">{label}: —</div>
    );
  }
  const min = Math.min(...numeric, 0);
  const max = Math.max(...numeric, 0);
  const range = max - min || 1;
  const w = Math.max(values.length * 16, 64);
  const h = 32;
  const step = values.length > 1 ? w / (values.length - 1) : w;

  const points: string[] = [];
  values.forEach((v, idx) => {
    if (typeof v === 'number' && !Number.isNaN(v)) {
      const x = idx * step;
      const y = h - ((v - min) / range) * h;
      points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
  });
  return (
    <div className="mt-2 flex items-center gap-2 text-xs text-muted-text">
      <span>{label}</span>
      <svg
        data-testid="alpha-sparkline"
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        className="text-blue-500"
      >
        {/* baseline @ y = 0 */}
        <line
          x1={0}
          x2={w}
          y1={h - ((0 - min) / range) * h}
          y2={h - ((0 - min) / range) * h}
          stroke="currentColor"
          strokeOpacity={0.2}
          strokeWidth={1}
        />
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth={1.6}
          points={points.join(' ')}
        />
      </svg>
    </div>
  );
};

export const DecisionTrackingTab: React.FC<DecisionTrackingTabProps> = ({
  stockCode,
  market,
  language = 'zh',
  initialEntries,
  api = decisionJournalApi,
  limit = 20,
}) => {
  const labels = useMemo(() => text(language), [language]);
  const [entries, setEntries] = useState<DecisionJournalEntry[] | null>(
    initialEntries ?? null,
  );
  const [loading, setLoading] = useState<boolean>(initialEntries === undefined);
  const [errored, setErrored] = useState<boolean>(false);

  useEffect(() => {
    // Test/seeded mode — initial state already reflects ``initialEntries``;
    // skip the fetch and let React keep using that snapshot.
    if (initialEntries !== undefined) return;
    if (!stockCode) return;
    let cancelled = false;
    api
      .list(stockCode, { market, limit })
      .then((res) => {
        if (cancelled) return;
        setEntries(res.entries || []);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setErrored(true);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stockCode, market, limit, api, initialEntries]);

  if (loading) {
    return (
      <section className="rounded-lg border border-border-color bg-card-bg p-4">
        <h3 className="mb-2 text-sm font-semibold text-primary-text">{labels.title}</h3>
        <p className="text-xs text-muted-text">{labels.loading}</p>
      </section>
    );
  }

  if (errored) {
    return (
      <section
        data-testid="decision-tracking-error"
        className="rounded-lg border border-rose-300 bg-rose-50/40 p-4"
      >
        <h3 className="mb-2 text-sm font-semibold text-rose-700">{labels.title}</h3>
        <p className="text-xs text-rose-700">{labels.error}</p>
      </section>
    );
  }

  const rows = entries || [];
  if (rows.length === 0) {
    return (
      <section
        data-testid="decision-tracking-empty"
        className="rounded-lg border border-border-color bg-card-bg p-4"
      >
        <h3 className="mb-2 text-sm font-semibold text-primary-text">{labels.title}</h3>
        <p className="text-xs text-muted-text">{labels.emptyState}</p>
      </section>
    );
  }

  // Sparkline uses oldest-first ordering for the natural left-to-right read.
  const alphas = [...rows]
    .slice()
    .reverse()
    .map((row) => row.alpha);

  return (
    <section
      data-testid="decision-tracking-tab"
      className="rounded-lg border border-border-color bg-card-bg p-4"
    >
      <h3 className="mb-3 text-sm font-semibold text-primary-text">{labels.title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-muted-text">
            <tr>
              <th className="py-1 pr-3 font-medium">{labels.columnDate}</th>
              <th className="py-1 pr-3 font-medium">{labels.columnVerdict}</th>
              <th className="py-1 pr-3 font-medium">{labels.columnScore}</th>
              <th className="py-1 pr-3 font-medium">{labels.columnRaw}</th>
              <th className="py-1 pr-3 font-medium">{labels.columnAlpha}</th>
              <th className="py-1 pr-3 font-medium">{labels.columnSummary}</th>
            </tr>
          </thead>
          <tbody className="text-primary-text">
            {rows.map((row, idx) => {
              const datePart = (row.decisionAt || '').split(' ')[0] || '—';
              const score = typeof row.score === 'number' ? row.score : '—';
              const verdict = row.verdict || '—';
              const rawPct = formatPercent(row.rawReturn);
              const alphaPct = formatPercent(row.alpha);
              const alphaTitle =
                row.alpha === null && row.rawReturn !== null
                  ? labels.alphaUnavailable
                  : undefined;
              const summary = (row.oneSentence || '').slice(0, 220);
              return (
                <tr key={`${row.decisionAt}-${idx}`} className="border-t border-border-color/40">
                  <td className="py-1 pr-3 align-top">{datePart}</td>
                  <td className="py-1 pr-3 align-top">{verdict}</td>
                  <td className="py-1 pr-3 align-top">{score}</td>
                  <td className="py-1 pr-3 align-top">{rawPct}</td>
                  <td
                    className={`py-1 pr-3 align-top ${alphaToneClass(row.alpha)}`}
                    title={alphaTitle}
                  >
                    {alphaPct}
                  </td>
                  <td className="py-1 pr-3 align-top text-muted-text">{summary}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <AlphaSparkline values={alphas} label={labels.sparkline} />
    </section>
  );
};

export default DecisionTrackingTab;
