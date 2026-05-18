import { useId, useState } from 'react';
import type { CommitteeDebateRounds } from '../../types/analysis';

interface CommitteeOptInProps {
  /** Whether the committee toggle is currently on. */
  enabled: boolean;
  /** Current debate round selection (1 / 2 / 3). */
  rounds: CommitteeDebateRounds;
  /** Persist toggle changes back to the store. */
  onEnabledChange: (enabled: boolean) => void;
  /** Persist round changes back to the store. */
  onRoundsChange: (rounds: CommitteeDebateRounds) => void;
  /** Disable interaction (e.g. while an analysis is in flight). */
  disabled?: boolean;
  /** Optional className for layout integration. */
  className?: string;
}

/**
 * Match the backend's effective LLM-call cap formula
 * (`src/agent/budget.compute_effective_cap`):
 *
 *     cap = base + 2 * (rounds - 1)
 *
 * where `base = INVESTMENT_COMMITTEE_BUDGET_BASE` (default 12).
 *
 * For UX we describe the *additional* cost on top of the default analysis,
 * which spec §9 expresses as `6 + 2*N + 2` (Bull + Bear * N + 4 lenses + Risk + PM).
 * The two formulas agree on the absolute call count; we keep the spec wording
 * verbatim in the hint string so the design doc and UI line up.
 */
const computeAdditionalCalls = (rounds: CommitteeDebateRounds): number =>
  6 + 2 * rounds + 2;

const ROUND_OPTIONS: ReadonlyArray<CommitteeDebateRounds> = [1, 2, 3];

/**
 * Sprint 1B opt-in disclosure for the Investment Committee multi-agent
 * pipeline. Collapsed by default so the existing single-click "分析" flow is
 * untouched for users who don't care about the committee.
 *
 * Product safety rule (spec §13 #7 / §7): every label uses the "inspired lens"
 * framing — never claim to channel the real Buffett / Burry / Wood / Taleb.
 */
export const CommitteeOptIn: React.FC<CommitteeOptInProps> = ({
  enabled,
  rounds,
  onEnabledChange,
  onRoundsChange,
  disabled = false,
  className,
}) => {
  // Disclosure auto-opens when the toggle is on so the round picker stays
  // visible after the user re-opens the form on a future visit.
  const [open, setOpen] = useState<boolean>(enabled);
  const switchId = useId();
  const roundsGroupId = useId();

  const additionalCalls = computeAdditionalCalls(rounds);

  return (
    <section
      data-testid="committee-opt-in"
      className={
        'rounded-xl border border-subtle bg-surface/60 px-3 py-2 text-xs text-secondary-text ' +
        (className ?? '')
      }
    >
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={`${switchId}-body`}
        className="flex w-full items-center justify-between gap-2 text-left text-foreground"
      >
        <span className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={
              'inline-block h-2 w-2 rounded-full ' +
              (enabled ? 'bg-primary' : 'bg-subtle')
            }
          />
          <span className="font-semibold">
            Advanced — Investment Committee (preview)
          </span>
        </span>
        <span aria-hidden="true" className="text-secondary-text">
          {open ? '▾' : '▸'}
        </span>
      </button>

      {open ? (
        <div id={`${switchId}-body`} className="mt-2 space-y-2">
          <label
            htmlFor={switchId}
            className="flex cursor-pointer items-center gap-2 select-none"
          >
            <input
              id={switchId}
              type="checkbox"
              role="switch"
              checked={enabled}
              disabled={disabled}
              onChange={(e) => onEnabledChange(e.target.checked)}
              aria-describedby={`${switchId}-hint`}
              className="h-3.5 w-3.5 rounded border-border accent-primary"
            />
            <span className="text-foreground">
              Convene the committee for this analysis
            </span>
          </label>

          <fieldset
            disabled={!enabled || disabled}
            className={
              'flex flex-col gap-1 ' + (!enabled ? 'opacity-50' : '')
            }
          >
            <legend className="text-secondary-text">Debate rounds</legend>
            <div
              role="radiogroup"
              aria-label="Bull/Bear debate rounds"
              id={roundsGroupId}
              className="flex gap-3"
            >
              {ROUND_OPTIONS.map((value) => {
                const id = `${roundsGroupId}-${value}`;
                return (
                  <label
                    key={value}
                    htmlFor={id}
                    className="flex cursor-pointer items-center gap-1"
                  >
                    <input
                      id={id}
                      type="radio"
                      name={roundsGroupId}
                      value={value}
                      checked={rounds === value}
                      disabled={!enabled || disabled}
                      onChange={() => onRoundsChange(value)}
                      className="h-3.5 w-3.5 accent-primary"
                    />
                    <span className="text-foreground">{value}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <p id={`${switchId}-hint`} className="text-secondary-text">
            <span data-testid="committee-cost-hint">
              ~{additionalCalls} extra LLM calls per stock
            </span>
            {' · '}
            <span>adds an Investment Committee Minutes section to the report.</span>
          </p>
        </div>
      ) : null}
    </section>
  );
};

export default CommitteeOptIn;
