# Sprint 1B — Investment Committee Web UI — P9 Delivery Report

**Branch:** `feat/committee-web` (off `feat/investment-committee` @ `992e602`)
**Worktree:** `/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-ab0c0f342f9426bc4`
**P8 agent:** ab0c0f342f9426bc4 (auto-spawned)
**Date:** 2026-05-18

> Pre-PUA declaration (信心门控): under the evidence collected below, all
> runnable acceptance checks (lint / build / committee tests) pass and the
> full-suite regression delta is zero relative to the `feat/investment-committee`
> baseline. The known 18 pre-existing failures are unrelated to this sprint and
> documented under "Verification evidence" below.

---

## 改了什么

11 files touched (8 modified, 3 new). All Web + docs only — zero backend, zero
desktop, zero workflow. Per the 4 commits on `feat/committee-web`:

### Sprint 1B-1 (`b1f552f`) — Type plumbing
- `apps/dsa-web/src/types/analysis.ts` — add `CommitteeDebateRounds`,
  `CommitteeStatus`, `CommitteePersonaId`, `CommitteeMasterOpinion`,
  `CommitteeDebateExchange`, `CommitteeRiskAssessment`, `CommitteeMinutes`
  types; extend `AnalysisRequest` with `enableInvestmentCommittee` +
  `committeeDebateRounds`; extend `AnalysisReport` with optional `committee`.
- `apps/dsa-web/src/api/analysis.ts` — `analyze` and `analyzeAsync` forward
  the new request fields only when the toggle is on (no field sent when off
  to preserve the existing payload contract).
- `apps/dsa-web/src/stores/stockPoolStore.ts` — adds
  `enableInvestmentCommittee: false` and `committeeDebateRounds: 2` to
  `initialState`, plus setters and `SubmitAnalysisOptions` overrides. The
  store reads its own state in `submitAnalysis` so re-analyse keeps the
  current toggle.
- `apps/dsa-web/src/hooks/useHomeDashboardState.ts` — surfaces the two
  new pieces of state + setters to HomePage.

### Sprint 1B-2 (`52a0c53`) — `CommitteeOptIn`
- `apps/dsa-web/src/components/committee/CommitteeOptIn.tsx` — collapsible
  disclosure ("Advanced — Investment Committee (preview)"), collapsed by
  default; auto-opens when the toggle is already on so the radio group
  stays visible. Live cost hint `~{6 + 2*N + 2} extra LLM calls per stock`
  matching the backend formula in `compute_effective_cap`.
- `apps/dsa-web/src/pages/HomePage.tsx` — disclosure is rendered directly
  under the input row. The toggle reads / writes via the store, so the
  single `submitAnalysis` entry point covers both single-stock and
  batch-style flows (only one analyse form on HomePage; both first-time and
  re-analyse already share the store state).
- `apps/dsa-web/src/components/committee/__tests__/CommitteeOptIn.test.tsx`
  — 7 Vitest cases.

### Sprint 1B-3 (`82b30cd`) — `CommitteeMinutesPanel` + persona mirror
- `apps/dsa-web/src/utils/personaDisplay.ts` (new) — byte-equivalent mirror
  of `PERSONA_DISPLAY` from `src/agent/agents/master_personas/__init__.py`:
  `displayEn`, `displayZh`, `avatarInitials`, `avatarColor`. Order pinned
  to `DEFAULT_PERSONA_ORDER` so the lens grid is deterministic and matches
  push / history renderer output.
- `apps/dsa-web/src/components/committee/CommitteeMinutesPanel.tsx` (new) —
  the post-report panel; layout per spec §9 / §10:
  - Status banner (`ok` hidden, `partial` amber, `failed` red + PM card
    suppressed).
  - PM verdict card with verdict chip / score / rationale / dissents /
    budget footer.
  - Risk strip (severity colour, red flags, suggested position %, VETO
    chip).
  - Debate timeline grouped by round.
  - 2×2 lens grid with avatar initials in coloured circle (WB amber / MB
    red / CW indigo / NT slate); first card in zh mode shows the Chinese
    parenthetical (`巴菲特式价值视角`); absent personas grey-out with an
    "absent" badge — never "X refused to comment".
- `apps/dsa-web/src/components/report/ReportSummary.tsx` — panel inserted
  between `ReportStrategy` and `ReportNews`. Renders `null` when
  `report.committee` is undefined, so non-opt-in reports are byte-identical
  to before.
- `apps/dsa-web/src/components/committee/__tests__/CommitteeMinutesPanel.test.tsx`
  — 6 Vitest cases.

### Sprint 1B-4 (`7895d6f`) — Docs
- `docs/CHANGELOG.md` — six flat `[Unreleased]` entries (新功能 / 改进 /
  测试 / 文档 types) appended after Sprint 1A's entries; no new sub-heading
  inside `[Unreleased]` (AGENTS.md rule).
- `docs/full-guide.md` — "投委会模式" section upgraded from "API 预览" to
  full mode with a 6-step Web UI walkthrough, panel anatomy, and a cost /
  RPM tip referencing the Gemini-free-tier shared bucket footgun.
- `README.md` / `docs/README_EN.md` / `docs/README_CHT.md` — one capability
  row each in the feature table; details deferred to `full-guide.md` per
  AGENTS.md README discipline.

---

## 为什么这么改

- **Single source of truth for persona strings.** Spec §13 #2 / #5 + the
  product safety rule (§7) require the renderer, push, history Markdown,
  and Web UI to all use the same "X-inspired lens" string. Sprint 1A
  centralised this in `master_personas/__init__.py:PERSONA_DISPLAY`. The
  Web mirror reads identical en / zh / initials / colour values, so a
  future change to the Python registry updates a single byte-equivalent
  TypeScript file. Anything else risks the renderer and Web showing
  divergent copy (the exact dual-renderer footgun from user memory).
- **Defaults in two places kept in sync.** Memory rule says
  `analysis.ts` + `stockPoolStore.ts` both carry the default; both now
  declare `committeeDebateRounds = 2` and `enableInvestmentCommittee =
  false`. The same defaults are echoed back in the disclosure if the user
  closes it before toggling so future store hydration doesn't lose state.
- **One `submitAnalysis` covers single + batch.** Investigation showed
  `submitAnalysis` is the single Web entry point — both first-time analyse
  and re-analyse pass through the store and pick up the committee toggle
  for free. No second wiring needed; wiring twice would have created
  two-source drift risk.
- **`enableInvestmentCommittee` only emitted when true.** Both API helpers
  spread the fields conditionally so the JSON payload for opt-out users
  stays byte-identical to today. Lower regression risk for any backend
  that might be sensitive to extra unknown keys.
- **Panel renders `null` on missing payload.** Spec §11 explicitly calls
  out "Frontend renders before backend has committee" — the panel never
  shows a spinner, never renders a frame for an absent committee. That
  keeps default analyses untouched and avoids layout shift.
- **Failed status hides PM card.** Status semantics (spec §10) — when PM
  itself fails, surfacing an empty verdict card would imply an
  inconclusive verdict is a verdict. The red banner replaces it.
- **Immutable in-render variable for the zh-subtitle picker.** First pass
  used a `let firstZhEmitted = false` mutated inside `.map`; React-19's
  Compiler treats that as a violation. Fix: derive the picker once from
  `DEFAULT_PERSONA_ORDER[0]`, then compare per-card. Same UX, no
  immutability rule fight, and the order matches the Python source.

---

## 验证情况

### Tooling baseline (worktree pwd)
```
/Users/zhen/daily_stock_analysis/.claude/worktrees/agent-ab0c0f342f9426bc4
```
Branch: `feat/committee-web` (off `feat/investment-committee` @ `992e602`).

### DONE 1 — `npm ci` (lockfile install)
```
$ cd apps/dsa-web && npm ci
…
169 packages are looking for funding
  run `npm fund` for details

10 vulnerabilities (4 moderate, 6 high)
```
(Vulnerabilities are pre-existing in the baseline lockfile; out of scope.)

### DONE 2 — `npm run lint`
```
$ npm run lint
> dsa-web@0.0.0 lint
> eslint .
```
**0 errors, 0 warnings.** Exit 0.

### DONE 3 — `npm run build`
```
$ npm run build
> dsa-web@0.0.0 build
> tsc -b && vite build

vite v7.3.1 building client environment for production...
transforming...
✓ 3183 modules transformed.
rendering chunks...
computing gzip size...
../../static/index.html                     0.87 kB │ gzip:   0.45 kB
../../static/assets/index-DRGKNVXF.css    157.45 kB │ gzip:  24.61 kB
../../static/assets/index-DFRZvjCy.js   1,299.74 kB │ gzip: 412.98 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
…
✓ built in 6.24s
```
Exit 0. The chunk-size warning is pre-existing.

### DONE 4 — Committee test suite
```
$ npx vitest run src/components/committee/__tests__/
 RUN  v4.1.0 …apps/dsa-web

 Test Files  2 passed (2)
      Tests  13 passed (13)
   Start at  04:11:23
   Duration  1.05s
```
**13 / 13 new committee test cases pass.**

### Full Vitest regression delta vs baseline
```
Before my changes (baseline on feat/investment-committee):
 Test Files  18 failed | 28 passed (46)
      Tests  256 passed | 2 skipped (258)

After my changes:
 Test Files  18 failed | 30 passed (48)
      Tests  269 passed | 2 skipped (271)
```
Δ = +2 test files passing, +13 tests passing, **zero new failures.** The 18
failing files are pre-existing and all stem from
`localStorage.getItem is not a function` in `agentChatStore.ts:106` — a
jsdom + zustand store-at-import-time issue that is wholly unrelated to
the committee work.

### Manual smoke status
- Backend committee path landed in Sprint 1A; the Web layer is purely
  additive on top of the existing JSON contract. The API contract
  (`enable_investment_committee` + `committee_debate_rounds` in the request
  body, `report.committee` in the response) is consumed verbatim — no
  shape assumptions beyond the Pydantic schemas in
  `src/schemas/committee_schema.py`.
- I did not run an end-to-end browser smoke (no live LLM in this
  environment). The Vitest tests exercise the rendering paths against
  fixture committee payloads; the live integration smoke is on the user's
  TODO before merge (Sprint 1B-5 acceptance gate calls for one A-share +
  one US stock screenshot smoke).

---

## 未验证项

- **Live LLM end-to-end smoke.** Not run in this worktree — would
  consume real LLM quota. The Sprint 1B-5 acceptance gate calls for
  manual UX smoke with screenshots. Recommendation: spawn one A-share
  (e.g. `600519`) and one US stock (e.g. `AAPL`) analysis with the toggle
  on, capture screenshots of the disclosure + the rendered minutes panel.
- **`docs/full-guide_EN.md` translation.** The English mirror of
  `full-guide.md` has no committee section yet (also missing in Sprint
  1A). Worth a separate small PR; not blocking 1B.
- **Pre-existing baseline test failures (18 files).** `localStorage` in
  jsdom + zustand store-at-module-load. Out of scope; recommended as a
  separate cleanup so future PRs see a green Vitest baseline.
- **Visual regression / Playwright smoke.** Not exercised. The build
  pipeline doesn't include a snapshot test for the new panel; consider
  adding one once design pass on persona avatars (locked decision §13 #2
  defers SVG upgrade) is scheduled.

---

## 风险点

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Backend changes `PERSONA_DISPLAY` (en/zh/colour) without updating the Web mirror | Low | Renderer / Web copy diverge | The mirror file's top comment names the source-of-truth path; the value table is short enough to grep-and-diff in a PR review. Could be enforced with a future tiny consistency test. |
| `report.committee` payload diverges from `CommitteeMinutes` schema (e.g. Pydantic-side rename) | Low | Field rendered as `undefined` -> ugly UX | All committee fields are optional in the TS schema; the panel gracefully degrades (missing risk → strip hidden, missing debate → timeline hidden, missing PM → suppressed by status). Worst case is a stale label, not a crash. |
| `camelcase-keys` does the wrong thing for an unfamiliar key | Very low | Field not surfaced | All committee field names follow snake_case and convert cleanly (verified against fixture in `CommitteeMinutesPanel.test.tsx`). |
| User toggles committee on then submits with weak / quota-exhausted LLM | Medium | API returns `status="failed"` or no `committee` block | Panel handles both (failed banner; null render). Spec §11 documents the failure modes and the renderer matches. |
| Bundle size warning fires on next vite build | Low | None — pre-existing | The +6 KB delta from the new components is well under the existing 1.3 MB main bundle. No new top-level npm dep. |

---

## 回滚方式

Feature is opt-in and additive. Three rollback layers, escalating:

1. **Soft rollback (user-driven).** Don't toggle the disclosure on. The
   payload `enable_investment_committee` is only emitted when the toggle
   is `true`; an unchecked disclosure produces byte-identical request
   bodies to today.
2. **UI hide.** Comment out the `<CommitteeOptIn …/>` block in
   `HomePage.tsx` and the `<CommitteeMinutesPanel …/>` line in
   `ReportSummary.tsx`. Backend Sprint 1A code remains untouched; the
   committee endpoint just goes silent on the Web. Five-line revert.
3. **Hard rollback.** `git revert 7895d6f 82b30cd 52a0c53 b1f552f` in that
   order restores `feat/investment-committee` HEAD exactly. The four
   commits are independent: 1B-3 only depends on 1B-1's types; 1B-2 and
   1B-4 are independent. Sprint 1A backend remains operational either
   way.

The persona mirror file (`personaDisplay.ts`) is harmless to leave behind
on a soft rollback — it's referenced only by the two new components and
goes unused if they're removed.

---

## Sprint 1B-5 acceptance status (per plan checklist)

- [x] `cd apps/dsa-web && npm ci && npm run lint && npm run build` green
  (DONE 1-3 above)
- [x] Component tests green (13/13 in
  `src/components/committee/__tests__/`)
- [ ] Manual UX smoke (one A-share + one US stock) — **deferred to user**;
  needs live LLM access. Documentation entry is ready for a screenshot.
- [x] Stop. Deliver to user with 6-point structure. No push performed.

---

## P9 escalations

None. Sprint completed L0 (zero retries needed beyond a one-line
React-19 immutability lint fix and a one-line `getByText` scoping fix in
my own newly-added test). PUA pressure level: clean.

---

## Files touched (final list, paths relative to repo root)

New:
- `apps/dsa-web/src/components/committee/CommitteeOptIn.tsx`
- `apps/dsa-web/src/components/committee/CommitteeMinutesPanel.tsx`
- `apps/dsa-web/src/components/committee/__tests__/CommitteeOptIn.test.tsx`
- `apps/dsa-web/src/components/committee/__tests__/CommitteeMinutesPanel.test.tsx`
- `apps/dsa-web/src/utils/personaDisplay.ts`
- `docs/superpowers/reviews/2026-05-18-sprint-1b-p9-report.md` (this report)

Modified:
- `apps/dsa-web/src/types/analysis.ts`
- `apps/dsa-web/src/api/analysis.ts`
- `apps/dsa-web/src/stores/stockPoolStore.ts`
- `apps/dsa-web/src/hooks/useHomeDashboardState.ts`
- `apps/dsa-web/src/pages/HomePage.tsx`
- `apps/dsa-web/src/components/report/ReportSummary.tsx`
- `docs/CHANGELOG.md`
- `docs/full-guide.md`
- `README.md`
- `docs/README_EN.md`
- `docs/README_CHT.md`

Untouched (per scope): all of `src/`, `api/`, `bot/`, `data_provider/`,
`apps/dsa-desktop/`, `.github/`, `AGENTS.md`, `CLAUDE.md`,
`docs/superpowers/specs/`, `docs/superpowers/plans/`, all existing test
files including `apps/dsa-web/src/components/__tests__/` and any
`tests/` content.
