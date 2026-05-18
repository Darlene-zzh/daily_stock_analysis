import { useState } from 'react';

import type {
  CommitteeDebateExchange,
  CommitteeMasterOpinion,
  CommitteeMinutes,
  CommitteePersonaId,
  CommitteeRiskAssessment,
  CommitteeVerdict,
  ReportLanguage,
} from '../../types/analysis';
import { DEFAULT_PERSONA_ORDER, PERSONA_DISPLAY } from '../../utils/personaDisplay';

interface CommitteeMinutesPanelProps {
  /** Optional committee payload from `report.committee` — renders null when absent. */
  committee?: CommitteeMinutes;
  /** Used to pick the Chinese parenthetical first-mention. */
  language?: ReportLanguage;
}

// ---------- helpers ---------------------------------------------------------

const VERDICT_LABEL: Record<CommitteeVerdict, { zh: string; en: string }> = {
  strong_buy: { zh: '强烈买入', en: 'Strong buy' },
  buy: { zh: '买入', en: 'Buy' },
  hold: { zh: '持有', en: 'Hold' },
  avoid: { zh: '回避', en: 'Avoid' },
  short: { zh: '做空', en: 'Short' },
};

const VERDICT_CHIP_CLASS: Record<CommitteeVerdict, string> = {
  strong_buy: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/30',
  buy: 'bg-green-500/15 text-green-700 border-green-500/30',
  hold: 'bg-yellow-500/15 text-yellow-700 border-yellow-500/30',
  avoid: 'bg-orange-500/15 text-orange-700 border-orange-500/30',
  short: 'bg-red-500/15 text-red-700 border-red-500/30',
};

const formatScore = (score: number | undefined): string =>
  typeof score === 'number' ? score.toFixed(1) : '—';

const formatPercent = (value: number | undefined): string =>
  typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';

const labelVerdict = (
  verdict: CommitteeVerdict | undefined,
  language: ReportLanguage,
): string => {
  if (!verdict) return language === 'en' ? 'No verdict' : '未给出结论';
  return VERDICT_LABEL[verdict][language];
};

// ---------- subcomponents --------------------------------------------------

interface StatusBannerProps {
  status: CommitteeMinutes['status'];
  missingAgents: string[];
  language: ReportLanguage;
}

const StatusBanner: React.FC<StatusBannerProps> = ({ status, missingAgents, language }) => {
  if (status === 'ok' || !status) {
    return null;
  }

  if (status === 'partial') {
    const count = missingAgents.length;
    return (
      <div
        data-testid="committee-status-banner"
        className="rounded-lg border border-amber-400/40 bg-amber-100/40 px-3 py-2 text-xs text-amber-900"
      >
        {language === 'en'
          ? `Committee delivered a verdict with ${count} agent${count === 1 ? '' : 's'} absent.`
          : `投委会在 ${count} 位成员缺席的情况下仍给出结论，请参考性使用。`}
      </div>
    );
  }

  return (
    <div
      data-testid="committee-status-banner"
      className="rounded-lg border border-red-400/40 bg-red-100/40 px-3 py-2 text-xs text-red-900"
    >
      {language === 'en'
        ? 'Committee inconclusive — treat as advisory only.'
        : '投委会无法形成有效结论，仅供参考。'}
    </div>
  );
};

interface PmVerdictCardProps {
  committee: CommitteeMinutes;
  language: ReportLanguage;
}

const PmVerdictCard: React.FC<PmVerdictCardProps> = ({ committee, language }) => {
  const verdict = committee.pmVerdict;
  return (
    <div
      data-testid="committee-pm-card"
      className="rounded-xl border border-subtle bg-surface/80 px-4 py-3"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-secondary-text">
          {language === 'en' ? 'Portfolio Manager verdict' : '组合经理决议'}
        </span>
        {verdict ? (
          <span
            className={
              'rounded-full border px-2 py-0.5 text-xs font-semibold ' +
              VERDICT_CHIP_CLASS[verdict]
            }
          >
            {labelVerdict(verdict, language)}
          </span>
        ) : null}
        <span className="text-xs text-secondary-text">
          {language === 'en' ? 'Score' : '评分'}{' '}
          <span className="font-mono text-foreground">{formatScore(committee.pmScore)}</span>
          {' / 10'}
        </span>
      </div>
      {committee.pmRationale ? (
        <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">
          {committee.pmRationale}
        </p>
      ) : null}
      {committee.pmDissents && committee.pmDissents.length > 0 ? (
        <p className="mt-2 text-xs text-secondary-text">
          {language === 'en' ? 'PM overruled:' : 'PM 否决：'}{' '}
          {committee.pmDissents.join(', ')}
        </p>
      ) : null}
      <p className="mt-2 text-[11px] text-muted-text">
        {language === 'en' ? 'Budget' : '预算'}{' '}
        <span className="font-mono">
          {committee.budgetUsed ?? 0} / {committee.budgetCap ?? 0}
        </span>
        {typeof committee.latencyMs === 'number' && committee.latencyMs > 0
          ? ` · ${(committee.latencyMs / 1000).toFixed(1)}s`
          : null}
      </p>
    </div>
  );
};

interface RiskStripProps {
  risk: CommitteeRiskAssessment | null | undefined;
  language: ReportLanguage;
}

const RiskStrip: React.FC<RiskStripProps> = ({ risk, language }) => {
  if (!risk) return null;
  const severity = risk.severity ?? 'none';
  const severityClass =
    severity === 'hard'
      ? 'border-red-500/40 bg-red-100/40 text-red-900'
      : severity === 'soft'
        ? 'border-amber-400/40 bg-amber-100/40 text-amber-900'
        : 'border-emerald-500/30 bg-emerald-100/30 text-emerald-900';

  const severityLabel = (() => {
    if (language === 'en') {
      return severity === 'hard'
        ? 'Hard'
        : severity === 'soft'
          ? 'Soft'
          : 'None';
    }
    return severity === 'hard' ? '硬风险' : severity === 'soft' ? '软风险' : '无风险';
  })();

  return (
    <div
      data-testid="committee-risk-strip"
      className={'rounded-xl border px-4 py-3 text-xs ' + severityClass}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="font-semibold">
          {language === 'en' ? 'Risk Manager' : '风险管理'}
        </span>
        <span className="rounded-full border border-current/30 px-2 py-0.5">
          {severityLabel}
        </span>
        {risk.veto ? (
          <span className="rounded-full border border-current/30 px-2 py-0.5 font-mono">
            VETO
          </span>
        ) : null}
        <span>
          {language === 'en' ? 'Suggested position' : '建议仓位'}{' '}
          <span className="font-mono">{formatPercent(risk.suggestedPositionPct)}</span>
        </span>
      </div>
      {risk.redFlags && risk.redFlags.length > 0 ? (
        <ul className="list-disc pl-4">
          {risk.redFlags.map((flag, index) => (
            <li key={index}>{flag}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

interface DebateTimelineProps {
  debate: CommitteeDebateExchange[] | undefined;
  language: ReportLanguage;
}

const DebateTimeline: React.FC<DebateTimelineProps> = ({ debate, language }) => {
  if (!debate || debate.length === 0) return null;
  // Group by round for compact display.
  const byRound = new Map<number, CommitteeDebateExchange[]>();
  for (const exchange of debate) {
    const list = byRound.get(exchange.roundIndex) ?? [];
    list.push(exchange);
    byRound.set(exchange.roundIndex, list);
  }
  const rounds = Array.from(byRound.keys()).sort((a, b) => a - b);

  return (
    <div
      data-testid="committee-debate-timeline"
      className="rounded-xl border border-subtle bg-surface/60 px-4 py-3"
    >
      <p className="mb-2 text-xs font-semibold text-foreground">
        {language === 'en' ? 'Bull vs Bear timeline' : '多空辩论时间线'}
      </p>
      <ol className="space-y-2">
        {rounds.map((round) => {
          const exchanges = byRound.get(round) ?? [];
          return (
            <li key={round} className="text-xs text-secondary-text">
              <p className="font-mono text-foreground">
                {language === 'en' ? `Round ${round}` : `第 ${round} 轮`}
              </p>
              {exchanges.map((exchange, index) => (
                <p key={index} className="ml-2 mt-0.5">
                  <span
                    className={
                      'mr-1 font-semibold ' +
                      (exchange.side === 'bull' ? 'text-emerald-700' : 'text-red-700')
                    }
                  >
                    {exchange.side === 'bull'
                      ? language === 'en'
                        ? 'Bull'
                        : '多方'
                      : language === 'en'
                        ? 'Bear'
                        : '空方'}
                    :
                  </span>
                  <span className="text-foreground">{exchange.claim ?? '—'}</span>
                </p>
              ))}
            </li>
          );
        })}
      </ol>
    </div>
  );
};

interface LensCardProps {
  personaId: CommitteePersonaId;
  opinion: CommitteeMasterOpinion | null;
  showChineseSubtitle: boolean;
  language: ReportLanguage;
}

const LensCard: React.FC<LensCardProps> = ({
  personaId,
  opinion,
  showChineseSubtitle,
  language,
}) => {
  const display = PERSONA_DISPLAY[personaId];
  const [expanded, setExpanded] = useState<boolean>(false);
  const isAbsent = !opinion || opinion.status === 'failed';

  return (
    <div
      data-testid={`committee-lens-card-${personaId}`}
      data-status={isAbsent ? 'absent' : 'present'}
      className={
        'flex flex-col gap-2 rounded-xl border px-4 py-3 ' +
        (isAbsent
          ? 'border-subtle bg-surface/40 text-secondary-text opacity-70'
          : 'border-subtle bg-surface/80 text-foreground')
      }
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
          style={{ backgroundColor: display.avatarColor }}
        >
          {display.avatarInitials}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{display.displayEn}</p>
          {showChineseSubtitle && language === 'zh' ? (
            <p className="truncate text-xs text-secondary-text">{display.displayZh}</p>
          ) : null}
        </div>
        {isAbsent ? (
          <span
            data-testid={`committee-lens-absent-${personaId}`}
            className="rounded-full border border-subtle px-2 py-0.5 text-[11px] uppercase tracking-wide text-secondary-text"
          >
            {language === 'en' ? 'absent' : '缺席'}
          </span>
        ) : opinion?.verdict ? (
          <span
            className={
              'rounded-full border px-2 py-0.5 text-xs font-semibold ' +
              VERDICT_CHIP_CLASS[opinion.verdict]
            }
          >
            {labelVerdict(opinion.verdict, language)}
          </span>
        ) : null}
      </div>

      {isAbsent ? null : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-secondary-text">
            <span>
              {language === 'en' ? 'Score' : '评分'}{' '}
              <span className="font-mono text-foreground">{formatScore(opinion?.score)}</span>
              {' / 10'}
            </span>
            {opinion?.toolsUsed && opinion.toolsUsed.length > 0 ? (
              <span className="font-mono text-muted-text">
                {opinion.toolsUsed.join(' · ')}
              </span>
            ) : null}
          </div>
          {opinion?.headline ? (
            <p className="text-sm leading-snug text-foreground">{opinion.headline}</p>
          ) : null}
          {opinion?.rationale || opinion?.counterView ? (
            <>
              <button
                type="button"
                onClick={() => setExpanded((prev) => !prev)}
                className="self-start text-xs font-medium text-primary hover:underline"
                aria-expanded={expanded}
              >
                {expanded
                  ? language === 'en'
                    ? 'Hide details'
                    : '收起详情'
                  : language === 'en'
                    ? 'Show rationale'
                    : '查看推理'}
              </button>
              {expanded ? (
                <div className="space-y-2 text-xs text-secondary-text">
                  {opinion?.rationale ? (
                    <p
                      className="whitespace-pre-line text-foreground"
                      data-testid={`committee-lens-rationale-${personaId}`}
                    >
                      {opinion.rationale}
                    </p>
                  ) : null}
                  {opinion?.keyEvidence && opinion.keyEvidence.length > 0 ? (
                    <ul className="list-disc pl-4">
                      {opinion.keyEvidence.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  ) : null}
                  {opinion?.counterView ? (
                    <p className="italic">
                      {language === 'en' ? 'What would change my mind: ' : '改变结论的条件：'}
                      {opinion.counterView}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </div>
  );
};

// ---------- main component -------------------------------------------------

/**
 * Sprint 1B Investment Committee minutes panel.
 *
 * Renders the `committee` payload attached to `report.committee` when the user
 * opts in. Always returns `null` when the payload is missing — that is the
 * graceful path (spec §11 "Frontend renders before backend has committee").
 *
 * Layout (spec §9): status banner → PM verdict card → debate timeline →
 * 4 lens cards → risk strip. The PM card is suppressed when `status="failed"`
 * so we don't surface an inconclusive verdict.
 */
export const CommitteeMinutesPanel: React.FC<CommitteeMinutesPanelProps> = ({
  committee,
  language = 'zh',
}) => {
  if (!committee) {
    return null;
  }

  const status = committee.status ?? 'ok';
  const missingAgents = committee.missingAgents ?? [];

  // Map persona id -> opinion for deterministic lens grid order.
  const opinionByPersona = new Map<CommitteePersonaId, CommitteeMasterOpinion>();
  for (const opinion of committee.masters ?? []) {
    opinionByPersona.set(opinion.persona, opinion);
  }

  // First Chinese parenthetical only on the first persona card in zh mode
  // (spec §13 #5 — keep English canonical, parenthetical on first mention).
  // Deterministic via DEFAULT_PERSONA_ORDER[0]; computed once, no in-render mutation.
  const zhSubtitlePersona: CommitteePersonaId | undefined = DEFAULT_PERSONA_ORDER[0];

  return (
    <section
      data-testid="committee-minutes-panel"
      data-status={status}
      className="space-y-3 rounded-2xl border border-subtle bg-surface/40 p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">
          {language === 'en'
            ? 'Investment Committee Minutes'
            : '投委会会议纪要'}
        </h2>
        <p className="text-[11px] uppercase tracking-wide text-muted-text">
          {language === 'en'
            ? `${committee.debateRounds ?? 0} debate round${(committee.debateRounds ?? 0) === 1 ? '' : 's'} · advisory only`
            : `辩论 ${committee.debateRounds ?? 0} 轮 · 仅供参考`}
        </p>
      </header>

      <StatusBanner
        status={status}
        missingAgents={missingAgents}
        language={language}
      />

      {status === 'failed' ? null : (
        <PmVerdictCard committee={committee} language={language} />
      )}

      <RiskStrip risk={committee.risk} language={language} />

      <DebateTimeline debate={committee.debate} language={language} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {DEFAULT_PERSONA_ORDER.map((personaId) => {
          const opinion = opinionByPersona.get(personaId) ?? null;
          return (
            <LensCard
              key={personaId}
              personaId={personaId}
              opinion={opinion}
              showChineseSubtitle={personaId === zhSubtitlePersona}
              language={language}
            />
          );
        })}
      </div>
    </section>
  );
};

export default CommitteeMinutesPanel;
