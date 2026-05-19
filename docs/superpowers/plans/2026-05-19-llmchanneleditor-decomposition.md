# LLMChannelEditor Medium+ Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx` (1803 lines, 14 react-doctor warnings) into a multi-file feature folder with ChannelRow sub-extracted into 3 panels, plus targeted a11y and perf fixes — taking the file to 3 remaining warnings.

**Architecture:** Create `src/components/settings/LLMChannelEditor/` folder holding types.ts, utils.ts, ChannelRow.tsx, 3 sub-panel files (ChannelTestPanel / ChannelDiscoveryPanel / ChannelCapabilityPanel), LLMChannelEditor.tsx, and index.ts. Tests move to `LLMChannelEditor/__tests__/`. The 37 existing vitest tests are the safety net at every commit.

**Tech Stack:** React 19, TypeScript 5.9, vitest, Tailwind 4, react-doctor (oxc-based lint), ESLint 9.

**Spec reference:** [docs/superpowers/specs/2026-05-19-llmchanneleditor-decomposition-design.md](../specs/2026-05-19-llmchanneleditor-decomposition-design.md)

---

## File Structure (locked in by spec)

After all 4 commits, the directory looks like:

```
apps/dsa-web/src/components/settings/LLMChannelEditor/
├── LLMChannelEditor.tsx           # main component, ~720 line function body (unchanged from current D1 state)
├── ChannelRow.tsx                 # orchestrator parent, ~200 lines after D2 sub-extraction
├── ChannelTestPanel.tsx           # NEW in D2 — connection test result UI, ~50 lines
├── ChannelDiscoveryPanel.tsx      # NEW in D2 — model discovery + checkbox list, ~80 lines
├── ChannelCapabilityPanel.tsx     # NEW in D2 — runtime capability checks, ~70 lines
├── types.ts                       # interfaces + UI option constants, ~95 lines
├── utils.ts                       # 31 pure helpers + 9 lookup tables, ~480 lines
├── index.ts                       # single-line re-export
└── __tests__/
    └── LLMChannelEditor.test.tsx  # moved from settings/__tests__/, ~1460 lines, 37 tests
```

External callers touched:
- `apps/dsa-web/src/components/settings/index.ts` — unchanged (folder resolution continues to work via the new `index.ts`)
- `apps/dsa-web/src/pages/SettingsPage.tsx:14` — import path updated to direct path

---

## Pre-flight (one-time, before D1)

### Task 0: Verify starting state

**Files:**
- Read: `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`

- [ ] **Step 1: Confirm file size and content layout**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
wc -l src/components/settings/LLMChannelEditor.tsx
```
Expected: `1803 src/components/settings/LLMChannelEditor.tsx`

If line count differs by more than ±5, the file has been modified since this plan was written. Read the file and re-verify the section boundaries before continuing.

- [ ] **Step 2: Confirm test baseline (37 passing)**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm test -- --run src/components/settings/__tests__/LLMChannelEditor.test.tsx 2>&1 | tail -5
```
Expected output ends with:
```
Test Files  1 passed (1)
     Tests  37 passed (37)
```

If fewer than 37 pass, do NOT proceed. Investigate the failing test first.

- [ ] **Step 3: Confirm current warning count (14 on this file)**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/baseline.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/baseline.json'))
diags = [x for x in d['diagnostics'] if 'LLMChannelEditor.tsx' in x['filePath']]
print(f'LLMChannelEditor warnings: {len(diags)}')
"
```
Expected: `LLMChannelEditor warnings: 14`

If the number is different, the spec's plan may not produce the target final state. Stop and reconcile with the spec author.

---

## D1: Architecture Migration

**Goal:** Move types, utils, ChannelRow, and main editor into `LLMChannelEditor/` folder. Zero behavior change. All 37 tests continue passing.

### Task 1: Create `types.ts`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/types.ts`

- [ ] **Step 1: Create the new folder**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
mkdir -p src/components/settings/LLMChannelEditor
```

- [ ] **Step 2: Write types.ts with the exact content below**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/types.ts`

Content — start with this header, then copy the listed line ranges from the original file verbatim:

```typescript
import type { ChannelProtocol } from '../llmProviderTemplates';
import type { LLMCapabilityCheck, LLMCapabilityCheckResult } from '../../../types/systemConfig';

// === UI option constants (from original LLMChannelEditor.tsx) ===

```

Then append, **verbatim from `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`**:
- Lines 24-31 (`const PROTOCOL_OPTIONS: ...`)
- Empty line
- Lines 59-64 (`const RUNTIME_CAPABILITY_OPTIONS: ...`)
- Empty line
- Lines 66-70 (`const CAPABILITY_STATUS_LABELS: ...`)
- Empty line, then heading comment `// === Interfaces ===`, empty line
- Lines 72-80 (`interface ChannelConfig`)
- Empty line
- Lines 82-86 (`interface ChannelTestState`)
- Empty line
- Lines 88-93 (`interface ChannelDiscoveryState`)
- Empty line
- Lines 95-101 (`interface ChannelCapabilityState`)
- Empty line
- Lines 103-109 (`interface RuntimeConfig`)
- Empty line
- Lines 111-117 (`interface LLMChannelEditorProps`)
- Empty line
- Lines 119-136 (`interface ChannelRowProps`)
- Empty line
- Lines 603-607 (`interface ParsedModelRef`)

**Important transformation**: Add `export ` in front of every `const`, `interface` declaration so all are exported.

Final file should be ~95 lines, end with a single trailing newline.

- [ ] **Step 3: Type-check the new file in isolation**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/types.ts 2>&1 | head -10
```
Expected: no output (file compiles standalone).

If errors, they will likely be about the relative import paths. Confirm:
- `'../llmProviderTemplates'` resolves to `apps/dsa-web/src/components/settings/llmProviderTemplates.ts`
- `'../../../types/systemConfig'` resolves to `apps/dsa-web/src/types/systemConfig.ts`

### Task 2: Create `utils.ts`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

- [ ] **Step 1: Write utils.ts with the exact import header below**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

```typescript
import type { ChannelProtocol } from '../llmProviderTemplates';
import type { LLMCapabilityCheck, LLMCapabilityCheckResult } from '../../../types/systemConfig';
import type { ChannelConfig, RuntimeConfig, ParsedModelRef } from './types';

```

- [ ] **Step 2: Append helper constants verbatim from original file**

Append, **verbatim from `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`**:
- Lines 33-55 (`const KNOWN_MODEL_PREFIXES = new Set([...])`)
- Empty line
- Lines 57 (`const FALSEY_VALUES = new Set([...]);`)
- Empty line
- Lines 658-665 (`const PROTOCOL_ALIASES: ...`)
- Empty line
- Lines 704-712 (`const LLM_STAGE_LABELS: ...`)
- Empty line
- Lines 714-727 (`const LLM_ERROR_LABELS: ...`)
- Empty line
- Lines 729-738 (`const LLM_TROUBLESHOOTING_HINTS: ...`)
- Empty line
- Lines 740-753 (`const LLM_REASON_HINTS: ...`)
- Empty line
- Lines 844 (`const MANAGED_PROVIDERS = new Set([...]);`)
- Lines 845-851 (`const LEGACY_PROVIDER_KEYS: ...`)

All constants should be **module-private** (no `export`) since they're only consumed by the helpers in this file.

- [ ] **Step 3: Append 31 helper functions verbatim**

Append the following line ranges from the original file, **each prefixed with `export `**:
- Lines 542-569 (`function normalizeProtocol`)
- Lines 571-587 (`function inferProtocol`)
- Lines 589-594 (`function parseEnabled`)
- Lines 596-601 (`function splitModels`)
- Lines 609-632 (`function parseModelRef`)
- Lines 634-641 (`function getModelComparisonKey`)
- Lines 643-647 (`function areModelsEquivalent`)
- Lines 649-656 (`function toggleModelSelection`)
- Lines 667-687 (`function normalizeModelForRuntime`)
- Lines 689-691 (`function resolveModelPreview`)
- Lines 693-702 (`function buildModelOptions`)
- Lines 755-757 (`function getLlmStageLabel`)
- Lines 759-761 (`function getLlmErrorCodeLabel`)
- Lines 763-782 (`function getLlmTroubleshootingHint`)
- Lines 784-803 (`function buildLlmTestHint`)
- Lines 805-817 (`function buildLlmFailureText`)
- Lines 819-823 (`function getCapabilityResultVariant`)
- Lines 825-831 (`function summarizeCapabilityResults`)
- Lines 833-842 (`function getFirstCapabilityHint`)
- Lines 853-857 (`function getRuntimeProvider`)
- Lines 859-862 (`function usesDirectEnvProvider`)
- Lines 864-870 (`function hasLegacyRuntimeSource`)
- Lines 872-876 (`function isRuntimeModelAvailable`)
- Lines 878-901 (`function sanitizeRuntimeConfigForSave`)
- Lines 903-909 (`function runtimeConfigsAreEqual`)
- Lines 911-936 (`function resolveTemperatureFromItems`)
- Lines 938-947 (`function normalizeAgentPrimaryModel`)
- Lines 949-958 (`function parseRuntimeConfigFromItems`)
- Lines 960-983 (`function parseChannelsFromItems`)
- Lines 985-1031 (`function channelsToUpdateItems`)
- Lines 1033-1041 (`function channelsAreEqual`)

**Important transformation**: Skip line 603-607 (the `interface ParsedModelRef`) — that already lives in types.ts.

Final file should be ~480 lines.

- [ ] **Step 4: Type-check utils.ts**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/utils.ts 2>&1 | head -10
```
Expected: no output.

### Task 3: Create `ChannelRow.tsx` (D1 version, no internal sub-extraction)

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelRow.tsx`

- [ ] **Step 1: Write the import header**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelRow.tsx`

```typescript
import type React from 'react';
import type { LLMCapabilityCheck } from '../../../types/systemConfig';
import { Badge } from '../../common/Badge';
import { Button } from '../../common/Button';
import { InlineAlert } from '../../common/InlineAlert';
import { Input } from '../../common/Input';
import { Select } from '../../common/Select';
import { StatusDot } from '../../common/StatusDot';
import { Tooltip } from '../../common/Tooltip';
import type { ChannelRowProps } from './types';
import {
  PROTOCOL_OPTIONS,
  RUNTIME_CAPABILITY_OPTIONS,
  CAPABILITY_STATUS_LABELS,
} from './types';
import {
  normalizeProtocol,
  splitModels,
  resolveModelPreview,
  areModelsEquivalent,
  toggleModelSelection,
  getLlmStageLabel,
  getLlmErrorCodeLabel,
  buildLlmTestHint,
  getCapabilityResultVariant,
  summarizeCapabilityResults,
} from './utils';

```

If during implementation TypeScript reports any other unresolved imports, look back at the original file's top-level imports (lines 1-22) and add what's missing.

- [ ] **Step 2: Append the ChannelRow component verbatim**

Append lines **138-540** from `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx` verbatim, prefixed with `export ` so it becomes `export const ChannelRow: React.FC<ChannelRowProps> = ...`.

Final file should be ~430 lines.

- [ ] **Step 3: Type-check ChannelRow.tsx**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelRow.tsx 2>&1 | head -20
```
Expected: no output. If errors mention unused imports, prune them. If errors mention unresolved symbols, add the corresponding import to the header.

### Task 4: Create new `LLMChannelEditor.tsx` (in folder)

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`

- [ ] **Step 1: Write the import header**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`

```typescript
import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import type { ParsedApiError } from '../../../api/error';
import { getParsedApiError } from '../../../api/error';
import { systemConfigApi } from '../../../api/systemConfig';
import type { LLMCapabilityCheck } from '../../../types/systemConfig';
import { ApiErrorAlert } from '../../common/ApiErrorAlert';
import { Badge } from '../../common/Badge';
import { Button } from '../../common/Button';
import { InlineAlert } from '../../common/InlineAlert';
import { Select } from '../../common/Select';
import type { ChannelProtocol } from '../llmProviderTemplates';
import {
  LLM_PROVIDER_CAPABILITY_LABELS,
  LLM_PROVIDER_TEMPLATES,
  MODEL_PLACEHOLDERS_BY_PROTOCOL,
  getProviderTemplate,
  isKnownProviderTemplate,
} from '../llmProviderTemplates';
import type {
  ChannelConfig,
  ChannelTestState,
  ChannelDiscoveryState,
  ChannelCapabilityState,
  RuntimeConfig,
  LLMChannelEditorProps,
} from './types';
import {
  splitModels,
  resolveModelPreview,
  buildModelOptions,
  parseChannelsFromItems,
  parseRuntimeConfigFromItems,
  channelsToUpdateItems,
  channelsAreEqual,
  sanitizeRuntimeConfigForSave,
  runtimeConfigsAreEqual,
  normalizeAgentPrimaryModel,
  inferProtocol,
  isRuntimeModelAvailable,
  normalizeModelForRuntime,
  buildLlmFailureText,
  buildLlmTestHint,
  getLlmTroubleshootingHint,
  summarizeCapabilityResults,
  getFirstCapabilityHint,
} from './utils';
import { ChannelRow } from './ChannelRow';

```

- [ ] **Step 2: Append the main LLMChannelEditor component verbatim**

Append lines **1044-1803** from the original `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx` verbatim.

The original starts with `export const LLMChannelEditor: React.FC<LLMChannelEditorProps> = ({` — keep that `export const` exactly as-is.

Final file should be ~810 lines (header + main component).

- [ ] **Step 3: Type-check the new main file**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx 2>&1 | head -30
```
Expected: no output. If imports are flagged unused, prune; if symbols unresolved, add to imports.

### Task 5: Create `index.ts`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/index.ts`

- [ ] **Step 1: Write the 1-line re-export**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/index.ts`

```typescript
export { LLMChannelEditor } from './LLMChannelEditor';
```

That's the entire file. No trailing types/exports needed.

### Task 6: Move the test file into the new folder

**Files:**
- Move: `apps/dsa-web/src/components/settings/__tests__/LLMChannelEditor.test.tsx` → `apps/dsa-web/src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx`

- [ ] **Step 1: Create the test subfolder and move the file**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
mkdir -p src/components/settings/LLMChannelEditor/__tests__
git mv src/components/settings/__tests__/LLMChannelEditor.test.tsx src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx
```

Use `git mv` (not plain `mv`) so git tracks the move as a rename rather than delete+add.

- [ ] **Step 2: Verify the test file's import paths still resolve**

The test file uses `import { LLMChannelEditor } from '../LLMChannelEditor';`. From the new location, `'../LLMChannelEditor'` resolves to `src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`. No edit needed.

Other imports in the test (like `from '../../../api/systemConfig'`) need verification — from the new location, those paths shift by one level. Open the test file and adjust any imports that referenced `'../../api/...'` (two levels up from `settings/__tests__/`) to `'../../../api/...'` (three levels up from `settings/LLMChannelEditor/__tests__/`).

Check the test file's top 20 lines:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
head -20 src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx
```

For every relative import starting with `'../../`, add one more `../`. For imports starting with `'./` or `'../`, examine case by case.

Likely changes (verify and apply):
- `from '../LLMChannelEditor'` → `from '../LLMChannelEditor'` (unchanged — resolves to new location)
- `from '../../api/systemConfig'` → `from '../../../api/systemConfig'`
- `from '../../api/error'` → `from '../../../api/error'`
- `from '../../types/systemConfig'` → `from '../../../types/systemConfig'`
- `from '../../utils/...'` → `from '../../../utils/...'`

### Task 7: Update `SettingsPage.tsx` import path

**Files:**
- Modify: `apps/dsa-web/src/pages/SettingsPage.tsx:14`

- [ ] **Step 1: Read the current import line**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
sed -n '14p' src/pages/SettingsPage.tsx
```
Expected: `import { LLMChannelEditor } from '../components/settings/LLMChannelEditor';`

- [ ] **Step 2: Update the import to use direct path**

Edit `apps/dsa-web/src/pages/SettingsPage.tsx`:
- Find: `import { LLMChannelEditor } from '../components/settings/LLMChannelEditor';`
- Replace with: `import { LLMChannelEditor } from '../components/settings/LLMChannelEditor/LLMChannelEditor';`

The direct path bypasses the folder's `index.ts` re-export so react-doctor's `no-barrel-import` rule doesn't fire on this importer.

### Task 8: Delete the old `LLMChannelEditor.tsx`

**Files:**
- Delete: `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`

- [ ] **Step 1: Remove the old file**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
git rm src/components/settings/LLMChannelEditor.tsx
```

After this, the only `LLMChannelEditor.tsx` left is at `src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`.

### Task 9: Verify D1 + Commit

- [ ] **Step 1: Run lint**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm run lint
```
Expected: no warnings or errors, just the standard `> dsa-web@0.0.0 lint\n> eslint .` output.

- [ ] **Step 2: Run build**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm run build 2>&1 | tail -10
```
Expected: `✓ built in <N>s` at the end, no errors.

If TypeScript reports unresolved imports, fix the import path in the offending file and re-run.

- [ ] **Step 3: Run the 37 LLMChannelEditor tests**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm test -- --run src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx 2>&1 | tail -5
```
Expected:
```
Test Files  1 passed (1)
     Tests  37 passed (37)
```

If any test fails, do NOT commit. Investigate — typical cause is a mis-routed import in either the moved test or the new component files.

- [ ] **Step 4: Verify react-doctor warning count unchanged at 14**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/post-d1.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/post-d1.json'))
diags = [x for x in d['diagnostics'] if 'LLMChannelEditor' in x['filePath']]
print(f'LLMChannelEditor warnings after D1: {len(diags)}')
for x in diags:
    print(f\"  {x['filePath']}:{x['line']}  {x['rule']}\")
"
```
Expected: 14 warnings total across the new folder's files. (D1 is pure architectural move; warning count doesn't change.)

- [ ] **Step 5: Commit D1**

```bash
cd /Users/zhen/daily_stock_analysis
git add apps/dsa-web/src/components/settings/LLMChannelEditor \
        apps/dsa-web/src/pages/SettingsPage.tsx
git status --short
git commit -m "refactor(web): move LLMChannelEditor into feature folder

Decompose the 1803-line src/components/settings/LLMChannelEditor.tsx
into a co-located feature folder:
  - LLMChannelEditor/types.ts      (interfaces + UI option constants)
  - LLMChannelEditor/utils.ts      (31 pure helpers + 9 lookup tables)
  - LLMChannelEditor/ChannelRow.tsx     (sub-component, unchanged size)
  - LLMChannelEditor/LLMChannelEditor.tsx  (main, ~810 lines)
  - LLMChannelEditor/index.ts      (single re-export)
  - LLMChannelEditor/__tests__/    (37 vitest tests moved here)

Aligns with the StockAutocomplete/ folder pattern. SettingsPage.tsx
import updated to the direct path. settings/index.ts barrel still
works via folder index resolution.

Zero behavior change. No function-body lines moved, just file
boundaries. All 37 tests pass. react-doctor warning count on the
target file is unchanged at 14 (no-giant-component looks at function
body size, not file size — those warnings are consumed in D2)."
```

---

## D2: ChannelRow Sub-Extraction

**Goal:** Break the 403-line `ChannelRow` function body into one orchestrator (~200 lines) + 3 sub-panel components (~50/80/70 lines each) to make ChannelRow's `no-giant-component` warning drop below the rule threshold.

### Task 10: Identify the 3 JSX seams in ChannelRow

**Files:**
- Read: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelRow.tsx`

- [ ] **Step 1: Find the three render-region anchors**

Run:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
grep -n "testState\|discoveryState\|capabilityState\|onTest\|onDiscoverModels\|onCheckCapabilities\|onToggleCapability" src/components/settings/LLMChannelEditor/ChannelRow.tsx | head -30
```

Read the file to identify three distinct JSX subtrees that render:
1. **Test panel region**: where `testState` is consumed (the connection test result + the test button). Likely a block like `{testState ? <div>...</div> : null}` plus the trigger button. Find its open/close brace boundaries.
2. **Discovery panel region**: where `discoveryState` is consumed (model discovery button + result + the discovered-models checkbox list around line 386).
3. **Capability panel region**: where `capabilityState` is consumed (capability checks + check button + per-capability result rows).

- [ ] **Step 2: Capture the exact JSX blocks**

For each of the 3 regions, note:
- The opening line number (the outermost JSX wrapper for that section)
- The closing line number
- The props the JSX consumes from the parent (which ChannelRow props or computed values it uses)

Save these notes — the next 3 tasks each move one region out.

### Task 11: Create `ChannelTestPanel.tsx`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelTestPanel.tsx`

- [ ] **Step 1: Write the import header**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelTestPanel.tsx`

```typescript
import type React from 'react';
import { Button } from '../../common/Button';
import { InlineAlert } from '../../common/InlineAlert';
import type { ChannelConfig, ChannelTestState } from './types';

interface ChannelTestPanelProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  testState?: ChannelTestState;
  onTest: (channel: ChannelConfig, index: number) => void;
}

export const ChannelTestPanel: React.FC<ChannelTestPanelProps> = ({
  channel,
  index,
  busy,
  testState,
  onTest,
}) => {
  // JSX moved from ChannelRow.tsx test-panel region — fill in from Task 10 notes
  return (
    <>
      {/* test button + test result JSX from ChannelRow */}
    </>
  );
};
```

- [ ] **Step 2: Replace the placeholder JSX with the exact block from ChannelRow**

Copy the test-panel JSX region identified in Task 10 from ChannelRow.tsx into the `return (...)` body of `ChannelTestPanel`. Remove the unused `import { Button }` / `import { InlineAlert }` if the moved JSX doesn't use them. Add any other UI imports the moved JSX needs (e.g., `Tooltip` if used).

- [ ] **Step 3: Type-check the new sub-panel**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelTestPanel.tsx 2>&1 | head -10
```
Expected: no output.

### Task 12: Create `ChannelDiscoveryPanel.tsx`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelDiscoveryPanel.tsx`

- [ ] **Step 1: Write the import header**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelDiscoveryPanel.tsx`

```typescript
import type React from 'react';
import { Button } from '../../common/Button';
import { InlineAlert } from '../../common/InlineAlert';
import type { ChannelConfig, ChannelDiscoveryState } from './types';
import {
  areModelsEquivalent,
  toggleModelSelection,
  splitModels,
} from './utils';

interface ChannelDiscoveryPanelProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  discoveryState?: ChannelDiscoveryState;
  onDiscoverModels: (channel: ChannelConfig) => void;
  onUpdate: (index: number, field: keyof ChannelConfig, value: string | boolean) => void;
}

export const ChannelDiscoveryPanel: React.FC<ChannelDiscoveryPanelProps> = ({
  channel,
  index,
  busy,
  discoveryState,
  onDiscoverModels,
  onUpdate,
}) => {
  const discoveredModels = discoveryState?.models ?? [];
  const selectedModels = splitModels(channel.models);

  // JSX moved from ChannelRow.tsx discovery-panel region — fill in from Task 10 notes
  return (
    <>
      {/* discovery button + result + checkbox list JSX from ChannelRow */}
    </>
  );
};
```

- [ ] **Step 2: Replace the placeholder JSX with the exact block from ChannelRow**

Copy the discovery-panel JSX region from ChannelRow.tsx. Important: line 386 (`<label>可选模型（可多选）</label>`) is in this region — **keep it as a `<label>` for now**. The a11y fix (converting to `<fieldset><legend>`) happens in D3.

Adjust the local variable declarations (`discoveredModels`, `selectedModels`) to match what the original code computed inline.

- [ ] **Step 3: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelDiscoveryPanel.tsx 2>&1 | head -10
```
Expected: no output.

### Task 13: Create `ChannelCapabilityPanel.tsx`

**Files:**
- Create: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelCapabilityPanel.tsx`

- [ ] **Step 1: Write the import header**

Path: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelCapabilityPanel.tsx`

```typescript
import type React from 'react';
import { Button } from '../../common/Button';
import { InlineAlert } from '../../common/InlineAlert';
import { Tooltip } from '../../common/Tooltip';
import type { LLMCapabilityCheck } from '../../../types/systemConfig';
import type { ChannelConfig, ChannelCapabilityState } from './types';
import {
  RUNTIME_CAPABILITY_OPTIONS,
  CAPABILITY_STATUS_LABELS,
} from './types';
import { getCapabilityResultVariant } from './utils';

interface ChannelCapabilityPanelProps {
  channel: ChannelConfig;
  busy: boolean;
  capabilityState?: ChannelCapabilityState;
  onToggleCapability: (channel: ChannelConfig, capability: LLMCapabilityCheck) => void;
  onCheckCapabilities: (channel: ChannelConfig) => void;
}

export const ChannelCapabilityPanel: React.FC<ChannelCapabilityPanelProps> = ({
  channel,
  busy,
  capabilityState,
  onToggleCapability,
  onCheckCapabilities,
}) => {
  // JSX moved from ChannelRow.tsx capability-panel region — fill in from Task 10 notes
  return (
    <>
      {/* capability prefs + check button + per-capability result rows */}
    </>
  );
};
```

- [ ] **Step 2: Replace placeholder JSX with the capability region from ChannelRow**

Copy the capability-panel JSX region from ChannelRow.tsx.

- [ ] **Step 3: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelCapabilityPanel.tsx 2>&1 | head -10
```
Expected: no output.

### Task 14: Update `ChannelRow.tsx` to delegate to the 3 sub-panels

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelRow.tsx`

- [ ] **Step 1: Add imports for the 3 sub-panels**

Edit the import header of ChannelRow.tsx to add:
```typescript
import { ChannelTestPanel } from './ChannelTestPanel';
import { ChannelDiscoveryPanel } from './ChannelDiscoveryPanel';
import { ChannelCapabilityPanel } from './ChannelCapabilityPanel';
```

- [ ] **Step 2: Replace each JSX region with a sub-panel invocation**

For each of the 3 JSX regions identified in Task 10, replace the inline JSX with a sub-panel component call. Example for the test panel region:

```tsx
<ChannelTestPanel
  channel={channel}
  index={index}
  busy={busy}
  testState={testState}
  onTest={onTest}
/>
```

Similar pattern for discovery and capability panels — pass through the props each sub-panel needs (as declared in their `*PanelProps` interfaces from tasks 11-13).

- [ ] **Step 3: Prune unused imports in ChannelRow.tsx**

After the JSX moves out, ChannelRow likely no longer uses some of its imports (e.g., `InlineAlert`, the troubleshooting hint utilities, `RUNTIME_CAPABILITY_OPTIONS`, `CAPABILITY_STATUS_LABELS`, certain utils). Run a quick TypeScript check:

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelRow.tsx 2>&1 | head -20
```

TypeScript with `"noUnusedLocals": true` (verify in tsconfig) will report unused imports. Remove each one reported.

- [ ] **Step 4: Verify ChannelRow function body is now under 300 lines**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
wc -l src/components/settings/LLMChannelEditor/ChannelRow.tsx
```
Expected: 200-250 lines total file size; the function body (between `export const ChannelRow: React.FC<...> = ({...}) => {` and the closing `};`) should be ~180-200 lines.

### Task 15: Verify D2 + Commit

- [ ] **Step 1: Run lint + build + tests**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm run lint
npm run build 2>&1 | tail -5
npm test -- --run src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx 2>&1 | tail -5
```
Expected:
- lint clean
- build green
- 37 tests pass

- [ ] **Step 2: Verify react-doctor warnings — ChannelRow's no-giant-component should be gone**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/post-d2.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/post-d2.json'))
diags = [x for x in d['diagnostics'] if 'LLMChannelEditor' in x['filePath']]
print(f'LLMChannelEditor folder warnings after D2: {len(diags)}')
gigantic = [x for x in diags if x['rule'] == 'no-giant-component']
print(f'no-giant-component: {len(gigantic)}')
for x in gigantic:
    print(f\"  {x['filePath']}:{x['line']}  {x['message'][:80]}\")
"
```
Expected: total 13 warnings, of which 1 is no-giant-component (only the main LLMChannelEditor component — ChannelRow's warning is gone).

- [ ] **Step 3: Commit D2**

```bash
cd /Users/zhen/daily_stock_analysis
git add apps/dsa-web/src/components/settings/LLMChannelEditor
git commit -m "refactor(web): split ChannelRow into 3 sub-panels

ChannelRow was 403 lines of function body, triggering react-doctor's
no-giant-component rule. Extract the 3 self-contained JSX regions
into dedicated sub-panel files:

  - ChannelTestPanel.tsx       — connection test trigger + result
  - ChannelDiscoveryPanel.tsx  — model discovery + checkbox list
  - ChannelCapabilityPanel.tsx — runtime capability checks + results

ChannelRow.tsx is now ~200 lines, an orchestrator that renders the
3 panels with prop pass-through. All 3 sub-panels are below the
no-giant-component threshold.

The line 386 group label issue (no-fieldset for the discovery
checkbox list) stays as <label> in this commit; the a11y fix
lands in the next commit. Behavior unchanged; 37 tests still pass.
react-doctor warnings on this folder: 14 -> 13."
```

---

## D3: Accessibility Fixes

**Goal:** Resolve 4 `label-has-associated-control` warnings — 2 via `htmlFor`+`id` linking, 2 via `<fieldset><legend>` group semantics. Visual output unchanged.

### Task 16: Locate the 4 a11y warning sites (fresh line numbers)

**Files:**
- Read: react-doctor diagnostics

- [ ] **Step 1: Re-run react-doctor to get post-D2 line numbers**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/post-d2.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/post-d2.json'))
diags = [x for x in d['diagnostics'] if x['rule']=='label-has-associated-control' and 'LLMChannelEditor' in x['filePath']]
print(f'label-has-associated-control: {len(diags)}')
for x in diags:
    print(f\"  {x['filePath']}:{x['line']}  {x['message'][:80]}\")
"
```

Expected output lists 4 occurrences. Note the exact file and line for each. These are the 4 sites to fix:
- Site A: `<label>协议</label>` next to a `<Select>` — in **ChannelRow.tsx**
- Site B: `<label>可选模型（可多选）</label>` above a checkbox grid — in **ChannelDiscoveryPanel.tsx**
- Site C: `<label>Temperature</label>` next to a `<input type="range">` — in **LLMChannelEditor.tsx**
- Site D: `<label>备选模型</label>` above a checkbox grid — in **LLMChannelEditor.tsx**

### Task 17: Fix Site A (协议 label in ChannelRow.tsx) with `htmlFor`+`id`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelRow.tsx`

- [ ] **Step 1: Add useId import**

Edit the top of `ChannelRow.tsx`:
- Find: `import type React from 'react';`
- Replace with: `import type React from 'react';\nimport { useId } from 'react';`

- [ ] **Step 2: Generate an id inside the component**

Inside the `ChannelRow` component body, near where other inputs are configured (right after the destructured props), add:
```tsx
const protocolSelectId = useId();
```

- [ ] **Step 3: Wire the label and Select together**

Find the JSX block from Site A. Replace the `<label>` and `<Select>` pair:

Before:
```tsx
<label className="block text-sm font-medium text-foreground">协议</label>
<Select
  value={channel.protocol}
  onChange={(v) => onUpdate(index, 'protocol', normalizeProtocol(v))}
  options={PROTOCOL_OPTIONS}
  disabled={busy}
  placeholder="选择协议"
/>
```

After:
```tsx
<label htmlFor={protocolSelectId} className="block text-sm font-medium text-foreground">协议</label>
<Select
  id={protocolSelectId}
  value={channel.protocol}
  onChange={(v) => onUpdate(index, 'protocol', normalizeProtocol(v))}
  options={PROTOCOL_OPTIONS}
  disabled={busy}
  placeholder="选择协议"
/>
```

- [ ] **Step 4: Verify `Select` component accepts an `id` prop (sanity check)**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
grep -nE "id\?: string|^interface SelectProps" src/components/common/Select.tsx | head -5
```

Expected: at least one match showing `id?: string;` in `SelectProps`. As of 2026-05-19 this prop already exists (used by `<Select id="runtime-primary-model" ...>` in the main editor). If for some reason it's been removed since then, add `id?: string;` to `SelectProps` and forward it to the rendered `<select id={id}>` element.

- [ ] **Step 5: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelRow.tsx 2>&1 | head -10
```
Expected: no output.

### Task 18: Fix Site B (可选模型 group label in ChannelDiscoveryPanel.tsx) with `<fieldset>`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/ChannelDiscoveryPanel.tsx`

- [ ] **Step 1: Replace the group label pattern with fieldset/legend**

Find the JSX block (from Task 16's Site B):
```tsx
<div>
  <label className="mb-2 block text-sm font-medium text-foreground">可选模型（可多选）</label>
  <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3">
    {discoveredModels.map((model) => (
      <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
        <input ... />
        <span>{model}</span>
      </label>
    ))}
  </div>
</div>
```

Replace with:
```tsx
<fieldset className="m-0 border-0 p-0">
  <legend className="mb-2 block text-sm font-medium text-foreground">可选模型（可多选）</legend>
  <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3">
    {discoveredModels.map((model) => (
      <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
        <input ... />
        <span>{model}</span>
      </label>
    ))}
  </div>
</fieldset>
```

Key changes:
- Outer `<div>` → `<fieldset>` with Tailwind reset (`m-0 border-0 p-0`) to neutralize the browser default fieldset chrome
- Inner first `<label>` → `<legend>` (preserves the styling classes from the original label)
- Inner `<input>` JSX unchanged

- [ ] **Step 2: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/ChannelDiscoveryPanel.tsx 2>&1 | head -10
```

### Task 19: Fix Site C (Temperature label in LLMChannelEditor.tsx) with `htmlFor`+`id`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`

- [ ] **Step 1: Add useId to the imports if missing**

Confirm the file already imports `useId`. If not, add it:
- Find: `import { useEffect, useMemo, useRef, useState } from 'react';`
- Replace with: `import { useEffect, useId, useMemo, useRef, useState } from 'react';`

- [ ] **Step 2: Add the id ref**

Inside `LLMChannelEditor` component body, near other state declarations:
```tsx
const temperatureInputId = useId();
```

- [ ] **Step 3: Wire label and input**

Find the JSX block (from Task 16 Site C):
```tsx
<label className="mb-1 block text-xs text-muted-text">Temperature</label>
<div className="flex items-center gap-3">
  <input
    type="range"
    min="0"
    max="2"
    step="0.1"
    value={runtimeConfig.temperature}
    disabled={busy}
    onChange={(event) => setRuntimeConfig((previous) => ({ ...previous, temperature: event.target.value }))}
    className="settings-input-checkbox h-1.5 flex-1 cursor-pointer rounded-full bg-border/60"
  />
  ...
</div>
```

Replace with (adding `htmlFor` + matching `id` on the input):
```tsx
<label htmlFor={temperatureInputId} className="mb-1 block text-xs text-muted-text">Temperature</label>
<div className="flex items-center gap-3">
  <input
    id={temperatureInputId}
    type="range"
    min="0"
    max="2"
    step="0.1"
    value={runtimeConfig.temperature}
    disabled={busy}
    onChange={(event) => setRuntimeConfig((previous) => ({ ...previous, temperature: event.target.value }))}
    className="settings-input-checkbox h-1.5 flex-1 cursor-pointer rounded-full bg-border/60"
  />
  ...
</div>
```

- [ ] **Step 4: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx 2>&1 | head -10
```

### Task 20: Fix Site D (备选模型 group in LLMChannelEditor.tsx) with `<fieldset>`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`

- [ ] **Step 1: Replace group label with fieldset/legend**

Find the JSX block (from Task 16 Site D):
```tsx
<div>
  <label className="mb-2 block text-xs text-muted-text">备选模型</label>
  <div className="space-y-2 rounded-xl border settings-border-strong settings-surface-overlay-soft p-3">
    {availableModels.map((model) => (
      <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
        <input ... />
        <span>{model}</span>
      </label>
    ))}
  </div>
</div>
```

Replace with:
```tsx
<fieldset className="m-0 border-0 p-0">
  <legend className="mb-2 block text-xs text-muted-text">备选模型</legend>
  <div className="space-y-2 rounded-xl border settings-border-strong settings-surface-overlay-soft p-3">
    {availableModels.map((model) => (
      <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
        <input ... />
        <span>{model}</span>
      </label>
    ))}
  </div>
</fieldset>
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx 2>&1 | head -10
```

### Task 21: Verify D3 + Commit

- [ ] **Step 1: Run lint + build + tests**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm run lint
npm run build 2>&1 | tail -5
npm test -- --run src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx 2>&1 | tail -5
```
Expected: lint clean, build green, 37 tests pass.

If any test fails on Site B or D (fieldset change), check whether the test queries `<label>` text explicitly — `screen.getByLabelText('可选模型（可多选）')` may need to become `screen.getByText('可选模型（可多选）')` because `<legend>` isn't treated the same as `<label>` by RTL. Update the test query if needed (but only if it's a test about THIS label's text, not a behavior assertion).

- [ ] **Step 2: Verify all 4 label warnings gone**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/post-d3.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/post-d3.json'))
diags = [x for x in d['diagnostics'] if x['rule']=='label-has-associated-control' and 'LLMChannelEditor' in x['filePath']]
print(f'label-has-associated-control remaining: {len(diags)}')
for x in diags:
    print(f\"  {x['filePath']}:{x['line']}\")
totals = [x for x in d['diagnostics'] if 'LLMChannelEditor' in x['filePath']]
print(f'LLMChannelEditor folder total: {len(totals)}')
"
```
Expected: `label-has-associated-control remaining: 0`, total: 9.

- [ ] **Step 3: Browser smoke (manual, optional but recommended)**

If a dev server is running locally, open Settings → LLM Channel section. Verify:
- Temperature range slider responds to label click (proves `htmlFor` works)
- Protocol Select dropdown opens when clicking the "协议" label (proves `htmlFor` works)
- "可选模型" and "备选模型" sections look identical to before (no fieldset border showing)

If you can't run the dev server, skip this and rely on test + lint coverage.

- [ ] **Step 4: Commit D3**

```bash
cd /Users/zhen/daily_stock_analysis
git add apps/dsa-web/src/components/settings/LLMChannelEditor
# If T17 Step 4 found Select needed an id prop and you added one, also stage:
#   git add apps/dsa-web/src/components/common/Select.tsx
git commit -m "fix(web): wire LLMChannel labels to controls for a11y

Resolve 4 react-doctor label-has-associated-control warnings:

  - ChannelRow.tsx 'protocol' Select: add useId() id + htmlFor pair.
    Select component already supports an id prop (existing pattern in
    the main editor's runtime-* Selects).
  - ChannelDiscoveryPanel.tsx 'discovered models' checkbox group:
    convert outer <div> + <label> into <fieldset><legend> so the
    group label has proper semantics. Tailwind border-0 m-0 p-0
    neutralizes the default fieldset chrome (visual no-op).
  - LLMChannelEditor.tsx Temperature range: useId() id + htmlFor pair.
  - LLMChannelEditor.tsx 'fallback models' checkbox group: same
    fieldset/legend treatment as discovery panel.

37 tests still pass (the RTL queries by label text remain valid
because <legend> + <fieldset> is still keyboard- and screen-reader-
accessible as a labelled group). react-doctor warnings on this
folder: 13 -> 9."
```

---

## D4: Performance Fixes

**Goal:** Resolve 6 performance warnings (2 `js-flatmap-filter` + 2 `js-set-map-lookups` + 2 `async-defer-await`), distinguishing real fixes from likely false positives that get inline `eslint-disable-next-line` comments with reasons.

### Task 22: Fix `splitModels` flatmap-filter chain

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

- [ ] **Step 1: Locate the current `splitModels` definition**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
grep -n "export function splitModels" src/components/settings/LLMChannelEditor/utils.ts
```

- [ ] **Step 2: Replace the body**

Find:
```typescript
export function splitModels(models: string): string[] {
  return models
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}
```

Replace with:
```typescript
export function splitModels(models: string): string[] {
  return models
    .split(',')
    .flatMap((entry) => {
      const trimmed = entry.trim();
      return trimmed ? [trimmed] : [];
    });
}
```

This collapses `.map().filter()` (two passes over the array) into a single `.flatMap()` pass.

### Task 23: Replace duplicated parse logic in `parseChannelsFromItems`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

- [ ] **Step 1: Locate the duplicated chain**

In `parseChannelsFromItems`, find the block:
```typescript
const channelNames = (itemMap.get('LLM_CHANNELS') || '')
  .split(',')
  .map((segment) => segment.trim())
  .filter(Boolean);
```

- [ ] **Step 2: Replace with direct `splitModels` call**

Replace the block with a single line:
```typescript
const channelNames = splitModels(itemMap.get('LLM_CHANNELS') || '');
```

This both kills the second `js-flatmap-filter` warning AND removes a copy of the same parse logic.

### Task 24: Convert `activeNames.includes()` to a `Set`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

- [ ] **Step 1: Locate the O(n²) site in `channelsToUpdateItems`**

Find the existing code:
```typescript
const activeNames = channels.map((channel) => channel.name.toUpperCase());

updates.push({ key: 'LLM_CHANNELS', value: channels.map((channel) => channel.name).join(',') });
// ...other setup...

for (const channel of channels) {
  // ... loop body ...
}

for (const oldName of previousChannelNames) {
  const upperName = oldName.toUpperCase();
  if (activeNames.includes(upperName)) {
    continue;
  }
  // ... cleanup body ...
}
```

- [ ] **Step 2: Convert `activeNames` to a Set and switch the lookup**

Replace:
```typescript
const activeNames = channels.map((channel) => channel.name.toUpperCase());
```

With:
```typescript
const activeNamesSet = new Set(channels.map((channel) => channel.name.toUpperCase()));
```

And update the lookup site inside the `for (const oldName of previousChannelNames)` loop:
```typescript
if (activeNamesSet.has(upperName)) {
  continue;
}
```

Set lookup is O(1) per call, eliminating the inner-loop O(n) `Array.includes` scan.

### Task 25: Add inline disable for the false-positive `String.includes`

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/utils.ts`

- [ ] **Step 1: Locate the `apiKey.includes(',')` line**

Search:
```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
grep -n "apiKey.includes" src/components/settings/LLMChannelEditor/utils.ts
```

Expected match: `const isMultiKey = channel.apiKey.includes(',');` inside the `channelsToUpdateItems` for-of loop.

- [ ] **Step 2: Add disable comment above the line**

Find:
```typescript
const isMultiKey = channel.apiKey.includes(',');
```

Replace with (insert a comment line before it):
```typescript
// eslint-disable-next-line react-doctor/js-set-map-lookups -- String.includes, not array lookup
const isMultiKey = channel.apiKey.includes(',');
```

Note: react-doctor's diagnostic prefix is `react-doctor/`. If the disable doesn't suppress the warning on the next react-doctor run, try `// react-doctor-disable-next-line js-set-map-lookups -- ...` or `// oxlint-disable-next-line js-set-map-lookups -- ...` depending on which suppression syntax the project uses (check existing disables in the repo with `grep -rn "react-doctor-disable\|oxlint-disable" apps/dsa-web/src | head`).

- [ ] **Step 3: Type-check + lint utils.ts**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx tsc --noEmit src/components/settings/LLMChannelEditor/utils.ts 2>&1 | head -5
npx --yes react-doctor@latest --json --full --offline . 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
diags = [x for x in d['diagnostics'] if x['rule']=='js-set-map-lookups' and 'LLMChannelEditor' in x['filePath']]
print(f'js-set-map-lookups remaining: {len(diags)}')
for x in diags: print(f\"  {x['filePath']}:{x['line']}\")
"
```
Expected: 0 remaining js-set-map-lookups warnings. If 1 remains and it's the same `apiKey.includes` line, the disable-comment syntax needs adjustment — try the alternates from Step 2.

### Task 26: Resolve the 2 async-defer-await warnings

**Files:**
- Modify: `apps/dsa-web/src/components/settings/LLMChannelEditor/LLMChannelEditor.tsx`

- [ ] **Step 1: Locate the 2 sites**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
diags = [x for x in d['diagnostics'] if x['rule']=='async-defer-await' and 'LLMChannelEditor' in x['filePath']]
for x in diags: print(f\"  {x['filePath']}:{x['line']}  {x['message'][:150]}\")
"
```

Expected: 2 diagnostics, both in LLMChannelEditor.tsx — one inside `handleDiscoverModels`, one inside `handleCapabilityCheck`.

- [ ] **Step 2: Read each site and decide real-fix vs. false-positive**

For each site, read the surrounding code (10-20 lines before and after the await). Check:
- Is there an early-`return` BEFORE the await that uses a condition NOT dependent on the awaited value?
- If yes → the await is correctly positioned (false positive). Apply disable-comment.
- If yes BUT the early-return is positioned AFTER the await → real fix: move the await down.
- If no early-return exists → likely false positive (the rule may be misfiring).

Per the spec's pre-analysis, both sites are likely false positives (`handleCapabilityCheck` has a guard at line 1472 already correctly positioned before the await; `handleDiscoverModels` has no guard at all).

- [ ] **Step 3a: If false positive — add disable comment**

For each false-positive site, add an inline disable directly above the offending `await` line:
```typescript
// eslint-disable-next-line react-doctor/async-defer-await -- guard at line N is already a sync early-return; setState before await is correct loading-spinner pattern
const result = await systemConfigApi.discoverLLMChannelModels({ ... });
```

Use a precise reason in the comment so a future reader understands why the rule was suppressed.

- [ ] **Step 3b: If real positive — restructure**

If the analysis in Step 2 reveals an actual structural issue (e.g., the early-return is downstream of the await and could be lifted), refactor to move the guard above the await. Run the 37 tests to ensure the restructure preserves behavior.

- [ ] **Step 4: Verify both async-defer-await warnings are gone**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
diags = [x for x in d['diagnostics'] if x['rule']=='async-defer-await' and 'LLMChannelEditor' in x['filePath']]
print(f'async-defer-await remaining: {len(diags)}')
"
```
Expected: 0.

### Task 27: Verify D4 + Commit

- [ ] **Step 1: Run lint + build + tests**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npm run lint
npm run build 2>&1 | tail -5
npm test -- --run src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx 2>&1 | tail -5
```
Expected: lint clean, build green, 37 tests pass.

- [ ] **Step 2: Verify full target reached — 3 warnings on this file/folder**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --full --offline . > /tmp/post-d4.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/post-d4.json'))
diags = [x for x in d['diagnostics'] if 'LLMChannelEditor' in x['filePath']]
print(f'LLMChannelEditor folder warnings after D4: {len(diags)}')
for x in diags:
    print(f\"  {x['filePath']}:{x['line']}  {x['rule']}\")
"
```
Expected: 3 warnings total. The 3 should be:
- One `no-giant-component` on `LLMChannelEditor.tsx` (the main editor's 760-line function body, explicitly deferred to Deep)
- One `prefer-useReducer` on `LLMChannelEditor.tsx` (12 useState calls, deferred to Deep)
- One `no-cascading-set-state` on `LLMChannelEditor.tsx` (the sync useEffect, deferred to Deep)

If a 4th warning appears, investigate before committing — likely an async-defer-await false-positive disable didn't take effect.

- [ ] **Step 3: Commit D4**

```bash
cd /Users/zhen/daily_stock_analysis
git add apps/dsa-web/src/components/settings/LLMChannelEditor
git commit -m "perf(web): batch perf cleanup on LLMChannelEditor utils/main

Resolve 6 react-doctor performance warnings:

  - utils.ts splitModels: .split().map().filter() -> .split().flatMap()
    Single-pass iteration instead of three.
  - utils.ts parseChannelsFromItems: replace duplicated
    .split().map().filter() with a direct splitModels() call,
    removing a copy of the parse logic.
  - utils.ts channelsToUpdateItems: convert activeNames to a Set so
    the .includes() inside the previousChannelNames loop becomes O(1).
    Real fix — eliminates an O(n*m) hot path on save.
  - utils.ts channelsToUpdateItems: apiKey.includes(',') flagged by
    js-set-map-lookups is a String.includes call, not array lookup.
    Inline disable-comment with reason.
  - LLMChannelEditor.tsx async-defer-await in handleDiscoverModels
    and handleCapabilityCheck: examined both; positions are correct
    for the loading-spinner setState pattern. Inline disable comments
    with reason.

Final react-doctor count on LLMChannelEditor folder: 9 -> 3. The
remaining 3 (no-giant-component on main editor, prefer-useReducer,
no-cascading-set-state) are deferred to a Deep-level topic since
they require structural state-shape changes."
```

---

## Final: CHANGELOG + summary

### Task 28: Update `docs/CHANGELOG.md`

**Files:**
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: Append entries to the `[Unreleased]` section**

Append the following lines just before the next `## [` version header in the `[Unreleased]` section of `docs/CHANGELOG.md`:

```markdown
- [chore] react-doctor Medium+ 重构 `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`：把 1803 行单文件拆为 `LLMChannelEditor/` feature folder（types.ts / utils.ts / ChannelRow.tsx / LLMChannelEditor.tsx / index.ts + 兄弟 `__tests__/`）；ChannelRow 内部再拆 `ChannelTestPanel` / `ChannelDiscoveryPanel` / `ChannelCapabilityPanel` 三个 sub-panel，函数体从 403 行降到 ~200 行。`SettingsPage.tsx` 改为直接路径 import。
- [改进] react-doctor a11y 修复 LLMChannelEditor 4 处 label-has-associated-control：协议 Select + Temperature range 用 `htmlFor`+`useId()` 关联（同时给 `Select` 组件加 `id` prop 透传到底层 `<select>`）；「可选模型」+「备选模型」两组 checkbox 列表改用 `<fieldset><legend>` 包整组，用 Tailwind `border-0 m-0 p-0` 抹掉默认样式。视觉无变化，37 个测试继续通过。
- [改进] react-doctor 性能修复 LLMChannelEditor utils：`splitModels` 与 `parseChannelsFromItems` 的 `.map().filter()` 合并为单遍 `.flatMap()`；`channelsToUpdateItems` 把 `activeNames` 改为 Set 让 `.includes()` 检查变 O(1)，消除 O(n*m) 热路径。2 处 `js-set-map-lookups` / `async-defer-await` 误报加 `eslint-disable-next-line` 注释 + 原因说明。该文件 react-doctor warning 从 14 降到 3。
```

Follow the project's existing `[Unreleased]` flat format (one line per entry, no `### 类目标题`).

- [ ] **Step 2: Commit**

```bash
cd /Users/zhen/daily_stock_analysis
git add docs/CHANGELOG.md
git commit -m "docs(changelog): note LLMChannelEditor Medium+ refactor

Append three [Unreleased] entries (chore / 改进 / 改进) for the
4-commit LLMChannelEditor decomposition: architecture move, ChannelRow
sub-extraction, a11y label fixes, perf cleanups. Net react-doctor
warnings on the target file: 14 -> 3 (the 3 remaining are deferred
to a Deep-level useReducer/state-shape topic)."
```

### Task 29: Final summary report

- [ ] **Step 1: Verify the full chain of commits**

```bash
cd /Users/zhen/daily_stock_analysis
git log --oneline -6
```
Expected (most recent first): 5 new commits — D1, D2, D3, D4, CHANGELOG — on top of the pre-implementation HEAD.

- [ ] **Step 2: Confirm web-wide warning count drop**

```bash
cd /Users/zhen/daily_stock_analysis/apps/dsa-web
npx --yes react-doctor@latest --json --offline . > /tmp/final.json 2>/dev/null
python3 -c "
import json
d = json.load(open('/tmp/final.json'))
print('SUMMARY:', d['summary'])
"
```
Expected: errors 0, warnings dropped from 124 (pre-implementation baseline) by 11. Final total ~113 warnings web-wide.

- [ ] **Step 3: Report**

Write a short summary back to the user:
- 5 commits landed
- Final LLMChannelEditor warnings: 14 → 3 (3 deferred to Deep)
- Web-wide warnings: 124 → ~113
- 37 LLMChannelEditor tests still pass
- Lint + build green

---

## Self-Review (run by author after writing this plan)

- [x] Spec coverage: every Medium+ scope item has a task — types extraction (T1), utils extraction (T2), ChannelRow move (T3), main editor move (T4), index re-export (T5), test move (T6), SettingsPage import (T7), old file delete (T8), ChannelRow sub-extraction (T10-T14), 4 a11y fixes (T16-T20), 6 perf fixes (T22-T26), CHANGELOG (T28)
- [x] Out-of-scope items NOT touched: useReducer migration, main editor sub-extraction, ChannelRow state lifting, ChatPage/PortfolioPage
- [x] No placeholders: every "TODO" reference is a structural reminder for the executor (e.g., "find current line number"), not unfinished plan content
- [x] Type consistency: `Select` `id` prop is added in T17 and used implicitly by main editor's Select instances (which already pass `id`) and ChannelRow's Select via T17's change
- [x] Verification gauntlet identical at each commit: lint + build + 37 tests + react-doctor diagnostic check
