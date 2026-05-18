import type { ReportLanguage } from '../../types/analysis';

/**
 * Sprint 4 — Structured Risk Assessment callout.
 *
 * Renders an independent risk panel (severity badge, suggested position %,
 * tail-risk score, 5% VaR, volatility, red-flag bullets) when the backend
 * attaches a `risk_assessment` payload via the `enable_structured_risk`
 * opt-in.  Returns `null` when the payload is absent so it can be wired
 * unconditionally into ReportSummary.
 *
 * Independent of the committee path — works even when committee is off.
 */

export interface StructuredRiskAssessment {
  severity?: 'none' | 'soft' | 'hard' | null;
  redFlags?: string[];
  suggestedPositionPct?: number | null;
  veto?: boolean;
  status?: 'ok' | 'failed';
  errorSummary?: string | null;
  tailRiskScore?: number | null;
  varEstimate5pct?: number | null;
  volatilityAnnualised?: number | null;
  rationale?: string | null;
}

interface StructuredRiskCalloutProps {
  /** Optional structured risk payload from `response.risk_assessment`. */
  riskAssessment?: StructuredRiskAssessment | null;
  /** Drives Chinese/English copy. */
  language?: ReportLanguage;
}

const text = (lang: ReportLanguage) => {
  const en = lang === 'en';
  return {
    title: en ? 'Risk Assessment' : '风险评估',
    severityLabel: en ? 'Severity' : '严重级别',
    positionLabel: en ? 'Suggested position' : '建议仓位',
    tailLabel: en ? 'Tail-risk score' : '尾部风险评分',
    varLabel: en ? '1-day 5% VaR' : '1 日 5% VaR',
    volLabel: en ? 'Ann. volatility' : '年化波动率',
    redFlagsLabel: en ? 'Red flags' : '风险信号',
    vetoLabel: 'veto=true',
    standaloneNote: en
      ? 'Standalone risk-manager output. Use alongside (not in place of) the main analysis.'
      : '独立风控视角的结构化判断，作为主分析的补充参考。',
  };
};

const SEVERITY_CLASS: Record<'none' | 'soft' | 'hard', string> = {
  none: 'bg-emerald-500/10 text-emerald-700 border border-emerald-500/30',
  soft: 'bg-amber-500/15 text-amber-800 border border-amber-500/30',
  hard: 'bg-red-500/15 text-red-700 border border-red-500/30',
};

const formatPercent = (
  value: number | null | undefined,
  digits = 1,
): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
};

const formatScore = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${value.toFixed(2)} / 10`;
};

export const StructuredRiskCallout: React.FC<StructuredRiskCalloutProps> = ({
  riskAssessment,
  language = 'zh',
}) => {
  // The single most important rule: render NOTHING when no payload is
  // attached. This lets ReportSummary include us unconditionally.
  if (!riskAssessment) {
    return null;
  }
  const labels = text(language);

  const severity = riskAssessment.severity ?? null;
  const severityClass =
    severity && SEVERITY_CLASS[severity] ? SEVERITY_CLASS[severity] : 'bg-subtle/40 text-muted-text';

  return (
    <section
      className="rounded-xl border border-subtle bg-card p-4 space-y-3"
      data-testid="structured-risk-callout"
      aria-label={labels.title}
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight">🛡️ {labels.title}</h3>
        <span
          className={`px-2 py-0.5 rounded-full text-[11px] uppercase tracking-wide ${severityClass}`}
          data-testid="structured-risk-severity"
        >
          {labels.severityLabel}: {severity ?? '—'}
          {riskAssessment.veto ? ` · ${labels.vetoLabel}` : ''}
        </span>
      </header>

      <p className="text-xs text-muted-text leading-snug">{labels.standaloneNote}</p>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted-text">{labels.positionLabel}</dt>
        <dd className="tabular-nums" data-testid="structured-risk-position">
          {formatPercent(riskAssessment.suggestedPositionPct)}
        </dd>
        {riskAssessment.tailRiskScore !== null
        && riskAssessment.tailRiskScore !== undefined && (
          <>
            <dt className="text-muted-text">{labels.tailLabel}</dt>
            <dd className="tabular-nums" data-testid="structured-risk-tail">
              {formatScore(riskAssessment.tailRiskScore)}
            </dd>
          </>
        )}
        {riskAssessment.varEstimate5pct !== null
        && riskAssessment.varEstimate5pct !== undefined && (
          <>
            <dt className="text-muted-text">{labels.varLabel}</dt>
            <dd className="tabular-nums" data-testid="structured-risk-var">
              {formatPercent(riskAssessment.varEstimate5pct, 2)}
            </dd>
          </>
        )}
        {riskAssessment.volatilityAnnualised !== null
        && riskAssessment.volatilityAnnualised !== undefined && (
          <>
            <dt className="text-muted-text">{labels.volLabel}</dt>
            <dd className="tabular-nums" data-testid="structured-risk-vol">
              {formatPercent(riskAssessment.volatilityAnnualised)}
            </dd>
          </>
        )}
      </dl>

      {riskAssessment.redFlags && riskAssessment.redFlags.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-muted-text">
            {labels.redFlagsLabel}
          </div>
          <ul className="text-xs space-y-0.5 list-disc list-inside text-foreground">
            {riskAssessment.redFlags.slice(0, 6).map((flag) => (
              <li key={flag} data-testid="structured-risk-flag">
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      {riskAssessment.rationale && (
        <blockquote
          className="border-l-2 border-subtle pl-3 text-xs italic text-muted-text"
          data-testid="structured-risk-rationale"
        >
          {riskAssessment.rationale}
        </blockquote>
      )}
    </section>
  );
};

export default StructuredRiskCallout;
