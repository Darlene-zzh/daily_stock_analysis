# 多主题视觉重设 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 dsa-web 前端从单一青色科技风升级为 4 套可切换主题（可爱 / 简约 / 高级 / 经典）× 明暗两模式，token 驱动、组件零逻辑改动、新模块自动继承。

**Architecture:** 双轴 token 系统——模式轴沿用现有 `next-themes` 的 `.dark` 类；家族轴用 `<html data-theme="...">` 由新增 `FamilyThemeProvider` 管理并持久化到 localStorage。CSS 用 `:root`/`.dark`（经典，回退）+ `[data-theme="X"]`/`[data-theme="X"].dark`（其余三套）覆盖语义 token。组件只读 `var(--*)`。

**Tech Stack:** React 18 / TypeScript / Tailwind CSS（`darkMode:['class']` + `@config`）/ next-themes / Vitest + React Testing Library。

**设计来源:** `docs/superpowers/specs/2026-06-02-multi-theme-visual-redesign-design.md`（配色 hex / token 契约 / 性格表为权威）。

**AGENTS.md 规则提醒:** commit message 英文、无 `Co-Authored-By`；未经确认不 `git push`/`git tag`；本地用 `python3.11`；前端验证 `cd apps/dsa-web && npm run lint && npm run build`，单测 `npx vitest run`（**CI 不跑 vitest，本地兜底**）；改完前端务必 `npm run build` 刷 bundle hash。

**分支:** `feat/multi-theme-visual-redesign`（spec 已在此分支 commit `e9eb976`）。

**Phase gate:** 每个 Phase 末尾停下来等用户确认再提交/继续（用户按 Phase gate 提交，非按 task）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `apps/dsa-web/src/components/theme/familyTheme.ts` | 家族常量、类型守卫、localStorage 读取、应用到 document 的纯函数 | 新建 |
| `apps/dsa-web/src/components/theme/FamilyThemeProvider.tsx` | React Context + `useThemeFamily()` | 新建 |
| `apps/dsa-web/src/components/theme/FamilyToggle.tsx` | 顶栏家族切换下拉 | 新建 |
| `apps/dsa-web/src/components/theme/__tests__/familyTheme.test.ts` | 纯函数单测 | 新建 |
| `apps/dsa-web/src/components/theme/__tests__/FamilyThemeProvider.test.tsx` | Provider 行为单测 | 新建 |
| `apps/dsa-web/src/components/theme/__tests__/FamilyToggle.test.tsx` | 切换组件单测 | 新建 |
| `apps/dsa-web/src/main.tsx` | 挂载 `FamilyThemeProvider` | 改 |
| `apps/dsa-web/index.html` | 首屏 FOUC 脚本扩展 `data-theme` | 改 |
| `apps/dsa-web/src/index.css` | 4 家族 × 明暗 token 块 + 新语义 token | 改 |
| `apps/dsa-web/tailwind.config.js` | `gain`/`loss`/`accent-brand`/`accent-brand-2` 颜色映射 | 改 |
| `apps/dsa-web/src/components/settings/ThemeFamilySelector.tsx` | 设置页 4 卡选择器 | 新建 |
| `apps/dsa-web/src/components/common/EmptyState.tsx`（或现有等价组件） | 可爱风专属空状态分支 | 改（Phase 4） |
| `docs/superpowers/reviews/2026-06-02-theme-migration-audit.md` | 硬编码色值审计清单 | 新建（Phase 3） |

---

# Phase 1 — Token 地基

> 目标：建好家族状态机 + 全部 token 值。完成后能用 React DevTools 手动改 `data-theme` 看到换肤，但 UI 上还没有切换入口。零可见行为变化（默认 premium）。

## Task 1.1: 家族常量与纯函数

**Files:**
- Create: `apps/dsa-web/src/components/theme/familyTheme.ts`
- Test: `apps/dsa-web/src/components/theme/__tests__/familyTheme.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// apps/dsa-web/src/components/theme/__tests__/familyTheme.test.ts
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_FAMILY,
  FAMILY_STORAGE_KEY,
  THEME_FAMILIES,
  isThemeFamily,
  readStoredFamily,
} from '../familyTheme';

describe('familyTheme', () => {
  it('exposes the four families and premium default', () => {
    expect(THEME_FAMILIES).toEqual(['classic', 'cute', 'minimal', 'premium']);
    expect(DEFAULT_FAMILY).toBe('premium');
  });

  it('isThemeFamily guards unknown values', () => {
    expect(isThemeFamily('cute')).toBe(true);
    expect(isThemeFamily('neon')).toBe(false);
    expect(isThemeFamily(null)).toBe(false);
  });

  it('readStoredFamily returns stored valid family', () => {
    const storage = { getItem: (k: string) => (k === FAMILY_STORAGE_KEY ? 'minimal' : null) };
    expect(readStoredFamily(storage)).toBe('minimal');
  });

  it('readStoredFamily falls back to default on garbage or throw', () => {
    expect(readStoredFamily({ getItem: () => 'bogus' })).toBe('premium');
    expect(readStoredFamily({ getItem: () => { throw new Error('blocked'); } })).toBe('premium');
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/familyTheme.test.ts`
Expected: FAIL（`Cannot find module '../familyTheme'`）

- [ ] **Step 3: 实现**

```ts
// apps/dsa-web/src/components/theme/familyTheme.ts
export type ThemeFamily = 'classic' | 'cute' | 'minimal' | 'premium';

export const THEME_FAMILIES: ThemeFamily[] = ['classic', 'cute', 'minimal', 'premium'];
export const DEFAULT_FAMILY: ThemeFamily = 'premium';
export const FAMILY_STORAGE_KEY = 'dsa-theme-family';

export function isThemeFamily(value: unknown): value is ThemeFamily {
  return typeof value === 'string' && (THEME_FAMILIES as string[]).includes(value);
}

export function readStoredFamily(storage: Pick<Storage, 'getItem'>): ThemeFamily {
  try {
    const value = storage.getItem(FAMILY_STORAGE_KEY);
    return isThemeFamily(value) ? value : DEFAULT_FAMILY;
  } catch {
    return DEFAULT_FAMILY;
  }
}

export function applyFamilyToDocument(family: ThemeFamily, root: HTMLElement): void {
  root.setAttribute('data-theme', family);
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/familyTheme.test.ts`
Expected: PASS（4 tests）

- [ ] **Step 5: 提交**

```bash
git add apps/dsa-web/src/components/theme/familyTheme.ts apps/dsa-web/src/components/theme/__tests__/familyTheme.test.ts
git commit -m "feat(web): theme family constants and pure helpers"
```

## Task 1.2: FamilyThemeProvider + useThemeFamily

**Files:**
- Create: `apps/dsa-web/src/components/theme/FamilyThemeProvider.tsx`
- Test: `apps/dsa-web/src/components/theme/__tests__/FamilyThemeProvider.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
// apps/dsa-web/src/components/theme/__tests__/FamilyThemeProvider.test.tsx
import { act, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FAMILY_STORAGE_KEY } from '../familyTheme';
import { FamilyThemeProvider, useThemeFamily } from '../FamilyThemeProvider';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <FamilyThemeProvider>{children}</FamilyThemeProvider>
);

describe('FamilyThemeProvider', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to premium and writes data-theme', () => {
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    expect(result.current.family).toBe('premium');
    expect(document.documentElement.getAttribute('data-theme')).toBe('premium');
  });

  it('hydrates from localStorage', () => {
    window.localStorage.setItem(FAMILY_STORAGE_KEY, 'cute');
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    expect(result.current.family).toBe('cute');
    expect(document.documentElement.getAttribute('data-theme')).toBe('cute');
  });

  it('setFamily updates state, storage and document', () => {
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    act(() => result.current.setFamily('minimal'));
    expect(result.current.family).toBe('minimal');
    expect(window.localStorage.getItem(FAMILY_STORAGE_KEY)).toBe('minimal');
    expect(document.documentElement.getAttribute('data-theme')).toBe('minimal');
  });

  it('throws when used outside provider', () => {
    expect(() => renderHook(() => useThemeFamily())).toThrow(/FamilyThemeProvider/);
  });

  it('renders children', () => {
    render(<FamilyThemeProvider><span>hi</span></FamilyThemeProvider>);
    expect(screen.getByText('hi')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/FamilyThemeProvider.test.tsx`
Expected: FAIL（`Cannot find module '../FamilyThemeProvider'`）

- [ ] **Step 3: 实现**

```tsx
// apps/dsa-web/src/components/theme/FamilyThemeProvider.tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  DEFAULT_FAMILY,
  FAMILY_STORAGE_KEY,
  applyFamilyToDocument,
  readStoredFamily,
  type ThemeFamily,
} from './familyTheme';

type FamilyThemeContextValue = {
  family: ThemeFamily;
  setFamily: (family: ThemeFamily) => void;
};

const FamilyThemeContext = createContext<FamilyThemeContextValue | null>(null);

export const FamilyThemeProvider = ({ children }: { children: ReactNode }) => {
  const [family, setFamilyState] = useState<ThemeFamily>(() =>
    typeof window === 'undefined' ? DEFAULT_FAMILY : readStoredFamily(window.localStorage)
  );

  const setFamily = useCallback((next: ThemeFamily) => {
    setFamilyState(next);
    try {
      window.localStorage.setItem(FAMILY_STORAGE_KEY, next);
    } catch {
      /* private mode / blocked storage — keep in-memory only */
    }
    applyFamilyToDocument(next, document.documentElement);
  }, []);

  useEffect(() => {
    applyFamilyToDocument(family, document.documentElement);
  }, [family]);

  const value = useMemo(() => ({ family, setFamily }), [family, setFamily]);

  return <FamilyThemeContext.Provider value={value}>{children}</FamilyThemeContext.Provider>;
};

export function useThemeFamily(): FamilyThemeContextValue {
  const ctx = useContext(FamilyThemeContext);
  if (!ctx) {
    throw new Error('useThemeFamily must be used within a FamilyThemeProvider');
  }
  return ctx;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/FamilyThemeProvider.test.tsx`
Expected: PASS（5 tests）

> 注：本仓库 jsdom 的 localStorage 需 `src/setupTests.ts` 的 MemoryStorage polyfill（已存在，见 [[repo-web-test-infra-gaps]]）。若报 `localStorage.getItem is not a function`，先确认 setupTests 已加载。

- [ ] **Step 5: 提交**

```bash
git add apps/dsa-web/src/components/theme/FamilyThemeProvider.tsx apps/dsa-web/src/components/theme/__tests__/FamilyThemeProvider.test.tsx
git commit -m "feat(web): FamilyThemeProvider with localStorage persistence"
```

## Task 1.3: 挂载 Provider

**Files:**
- Modify: `apps/dsa-web/src/main.tsx`

- [ ] **Step 1: 改 main.tsx**

把 `FamilyThemeProvider` 包在 `ThemeProvider` 内层（两者都写 `documentElement`，顺序无关；内层即可）：

```tsx
// apps/dsa-web/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from './components/theme/ThemeProvider'
import { FamilyThemeProvider } from './components/theme/FamilyThemeProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <ThemeProvider>
        <FamilyThemeProvider>
          <App />
        </FamilyThemeProvider>
      </ThemeProvider>
    </MotionConfig>
  </StrictMode>,
)
```

- [ ] **Step 2: 构建确认无回归**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功，无 TS 报错。

- [ ] **Step 3: 提交**

```bash
git add apps/dsa-web/src/main.tsx
git commit -m "feat(web): mount FamilyThemeProvider in app root"
```

## Task 1.4: 首屏 FOUC 脚本扩展 data-theme

**Files:**
- Modify: `apps/dsa-web/index.html`

- [ ] **Step 1: 在现有 theme 内联脚本里追加 data-theme 处理**

把 `index.html` `<head>` 里现有 IIFE 改成（新增 family 段，保留原 light/dark 逻辑）：

```html
    <script>
      (() => {
        const root = document.documentElement;
        // mode (light/dark)
        const storedTheme = localStorage.getItem('theme');
        const theme = storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : 'dark';
        root.classList.remove('light', 'dark');
        root.classList.add(theme);
        root.style.colorScheme = theme;
        // family (classic/cute/minimal/premium)
        const families = ['classic', 'cute', 'minimal', 'premium'];
        const storedFamily = localStorage.getItem('dsa-theme-family');
        const family = families.indexOf(storedFamily) !== -1 ? storedFamily : 'premium';
        root.setAttribute('data-theme', family);
      })();
    </script>
```

- [ ] **Step 2: 构建确认**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功。

- [ ] **Step 3: 提交**

```bash
git add apps/dsa-web/index.html
git commit -m "feat(web): set data-theme in head script to prevent FOUC"
```

## Task 1.5: index.css 新增语义 token + 经典补齐 + 三套家族块

**Files:**
- Modify: `apps/dsa-web/src/index.css`

> 说明：每个家族块**只覆盖核心语义 token**；大量 `--home-*`/`--settings-*` 等派生 token 因引用 `var(--primary)`/`var(--foreground)` 会自动跟随，无需在家族块里重复（剩余硬编码项由 Phase 3 收编）。`--gain-soft`/`--loss-soft` 不单独定义，组件用 `hsl(var(--gain) / 0.12)` 形式取淡色。

- [ ] **Step 1: 给 `:root`（经典·浅）追加新语义 token**

在 `:root { ... }` 内（紧跟现有 `--ring` 之后）追加：

```css
  /* === Multi-theme semantic tokens (classic light defaults) === */
  --accent-brand: 247 84% 66%;       /* classic 紫 */
  --accent-brand-2: 193 100% 43%;    /* classic 青（= primary） */
  --gain: 0 88% 62%;                 /* 涨·红（沿用 --home-price-up） */
  --loss: 149 100% 42%;              /* 跌·绿（沿用 --home-price-down） */
  --font-sans: "Inter", "SF Pro Display", "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-display: var(--font-sans);
  /* --radius 已存在 (1rem)；保持经典 16px */
```

- [ ] **Step 2: 给 `.dark`（经典·暗）追加对应值**

在 `.dark { ... }` 内追加：

```css
  /* === Multi-theme semantic tokens (classic dark) === */
  --accent-brand: 247 84% 72%;
  --accent-brand-2: 190 100% 50%;
  --gain: 0 88% 64%;
  --loss: 149 100% 44%;
  --font-sans: "Inter", "SF Pro Display", "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-display: var(--font-sans);
```

- [ ] **Step 3: 在 `.dark { ... }` 块之后追加三套家族块**

```css
/* =========================================
   THEME FAMILIES (data-theme)
   每块覆盖核心语义 token；派生 token 引用核心自动跟随。
   ========================================= */

/* ---------- PREMIUM（高级/中性，默认家族） ---------- */
[data-theme="premium"] {
  --background: 220 16% 96%;
  --card: 0 0% 100%;
  --card-foreground: 220 26% 16%;
  --popover: 0 0% 100%;
  --popover-foreground: 220 26% 16%;
  --elevated: 0 0% 100%;
  --hover: 216 17% 94%;
  --foreground: 220 26% 16%;
  --secondary: 216 17% 94%;
  --secondary-foreground: 220 26% 16%;
  --secondary-text: 220 17% 31%;
  --muted: 216 17% 94%;
  --muted-foreground: 220 8% 61%;
  --muted-text: 220 8% 61%;
  --accent: 216 17% 94%;
  --accent-foreground: 220 26% 16%;
  --border: 220 12% 90%;
  --input: 220 12% 90%;
  --ring: 210 25% 48%;
  --primary: 220 26% 16%;
  --primary-foreground: 42 31% 94%;
  --accent-brand: 210 25% 48%;      /* 钢蓝 */
  --accent-brand-2: 36 36% 52%;     /* 香槟金 */
  --gain: 6 63% 46%;
  --loss: 154 46% 34%;
  --radius: 0.625rem;               /* 10px */
  --font-sans: "Inter", system-ui, sans-serif;
  --font-display: "Fraunces", Georgia, "Times New Roman", serif;
}
[data-theme="premium"].dark {
  --background: 224 30% 7%;
  --card: 221 27% 12%;
  --card-foreground: 218 31% 95%;
  --popover: 221 27% 12%;
  --popover-foreground: 218 31% 95%;
  --elevated: 224 30% 15%;
  --hover: 220 23% 18%;
  --foreground: 218 31% 95%;
  --secondary: 220 23% 18%;
  --secondary-foreground: 218 31% 95%;
  --secondary-text: 218 16% 71%;
  --muted: 220 23% 18%;
  --muted-foreground: 220 9% 46%;
  --muted-text: 220 9% 46%;
  --accent: 220 23% 18%;
  --accent-foreground: 218 31% 95%;
  --border: 220 23% 18%;
  --input: 220 23% 18%;
  --ring: 210 31% 61%;
  --primary: 218 31% 95%;
  --primary-foreground: 222 28% 9%;
  --accent-brand: 210 31% 61%;
  --accent-brand-2: 40 55% 66%;
  --gain: 4 83% 65%;
  --loss: 151 50% 53%;
}

/* ---------- CUTE（可爱·草莓奶昔） ---------- */
[data-theme="cute"] {
  --background: 336 100% 97%;
  --card: 0 0% 100%;
  --card-foreground: 331 22% 29%;
  --popover: 0 0% 100%;
  --popover-foreground: 331 22% 29%;
  --elevated: 0 0% 100%;
  --hover: 334 100% 95%;
  --foreground: 331 22% 29%;
  --secondary: 334 100% 95%;
  --secondary-foreground: 331 22% 29%;
  --secondary-text: 333 17% 41%;
  --muted: 334 100% 95%;
  --muted-foreground: 334 13% 55%;
  --muted-text: 334 13% 55%;
  --accent: 334 100% 95%;
  --accent-foreground: 331 22% 29%;
  --border: 336 100% 93%;
  --input: 336 100% 93%;
  --ring: 334 100% 75%;
  --primary: 334 100% 75%;
  --primary-foreground: 0 0% 100%;
  --accent-brand: 336 71% 62%;      /* 深玫 */
  --accent-brand-2: 336 71% 62%;
  --gain: 344 100% 65%;
  --loss: 147 43% 52%;
  --radius: 1.125rem;               /* 18px */
  --font-sans: "Quicksand", "Nunito", system-ui, sans-serif;
  --font-display: "Quicksand", "Nunito", system-ui, sans-serif;
}
[data-theme="cute"].dark {
  --background: 225 16% 10%;
  --card: 224 18% 16%;
  --card-foreground: 216 42% 95%;
  --popover: 224 18% 16%;
  --popover-foreground: 216 42% 95%;
  --elevated: 223 18% 20%;
  --hover: 220 17% 24%;
  --foreground: 216 42% 95%;
  --secondary: 220 17% 24%;
  --secondary-foreground: 216 42% 95%;
  --secondary-text: 215 22% 81%;
  --muted: 220 17% 24%;
  --muted-foreground: 218 12% 60%;
  --muted-text: 218 12% 60%;
  --accent: 220 17% 24%;
  --accent-foreground: 216 42% 95%;
  --border: 220 17% 24%;
  --input: 220 17% 24%;
  --ring: 333 100% 78%;
  --primary: 333 100% 78%;
  --primary-foreground: 294 36% 11%;
  --accent-brand: 331 100% 83%;
  --accent-brand-2: 331 100% 83%;
  --gain: 341 100% 72%;
  --loss: 147 50% 58%;
}

/* ---------- MINIMAL（简约·纯黑白灰） ---------- */
[data-theme="minimal"] {
  --background: 0 0% 98%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 9%;
  --popover: 0 0% 100%;
  --popover-foreground: 0 0% 9%;
  --elevated: 0 0% 100%;
  --hover: 240 5% 96%;
  --foreground: 0 0% 9%;
  --secondary: 240 5% 96%;
  --secondary-foreground: 0 0% 9%;
  --secondary-text: 0 0% 25%;
  --muted: 240 5% 96%;
  --muted-foreground: 0 0% 45%;
  --muted-text: 0 0% 45%;
  --accent: 240 5% 96%;
  --accent-foreground: 0 0% 9%;
  --border: 0 0% 90%;
  --input: 0 0% 90%;
  --ring: 0 0% 9%;
  --primary: 0 0% 9%;
  --primary-foreground: 0 0% 100%;
  --accent-brand: 0 0% 9%;
  --accent-brand-2: 0 0% 9%;
  --gain: 0 72% 51%;
  --loss: 142 76% 36%;
  --radius: 0.5rem;                 /* 8px */
  --font-sans: "Inter", "Geist", system-ui, sans-serif;
  --font-display: var(--font-sans);
}
[data-theme="minimal"].dark {
  --background: 0 0% 4%;
  --card: 0 0% 9%;
  --card-foreground: 0 0% 98%;
  --popover: 0 0% 9%;
  --popover-foreground: 0 0% 98%;
  --elevated: 0 0% 11%;
  --hover: 0 0% 15%;
  --foreground: 0 0% 98%;
  --secondary: 0 0% 15%;
  --secondary-foreground: 0 0% 98%;
  --secondary-text: 0 0% 83%;
  --muted: 0 0% 15%;
  --muted-foreground: 240 5% 65%;
  --muted-text: 240 5% 65%;
  --accent: 0 0% 15%;
  --accent-foreground: 0 0% 98%;
  --border: 0 0% 15%;
  --input: 0 0% 15%;
  --ring: 0 0% 98%;
  --primary: 0 0% 98%;
  --primary-foreground: 0 0% 4%;
  --accent-brand: 0 0% 98%;
  --accent-brand-2: 0 0% 98%;
  --gain: 0 91% 71%;
  --loss: 142 69% 58%;
}
```

- [ ] **Step 4: 构建确认**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功，无 CSS 解析错误。

- [ ] **Step 5: 手动换肤验证（开发模式）**

Run: `cd apps/dsa-web && npm run dev`，浏览器打开后在 DevTools Console 执行 `document.documentElement.setAttribute('data-theme','cute')`，观察背景/主色变化；再试 `minimal`/`premium`；配合切 `.dark` 类验证暗色。
Expected: 背景、卡面、主色随 data-theme 改变（部分硬编码组件暂不变，属正常，Phase 3 收编）。

- [ ] **Step 6: 提交**

```bash
git add apps/dsa-web/src/index.css
git commit -m "feat(web): add semantic theme tokens and premium/cute/minimal family blocks"
```

## Task 1.6: Tailwind 暴露新语义颜色

**Files:**
- Modify: `apps/dsa-web/tailwind.config.js`

- [ ] **Step 1: 在 `theme.extend.colors` 里追加**

```js
        gain: 'hsl(var(--gain))',
        loss: 'hsl(var(--loss))',
        'accent-brand': 'hsl(var(--accent-brand))',
        'accent-brand-2': 'hsl(var(--accent-brand-2))',
```

- [ ] **Step 2: 在 `theme.extend` 里追加字体族映射**

```js
      fontFamily: {
        sans: ['var(--font-sans)'],
        display: ['var(--font-display)'],
      },
```

- [ ] **Step 3: 构建确认**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功；`bg-gain` / `text-loss` / `font-display` 等工具类可用。

- [ ] **Step 4: 提交**

```bash
git add apps/dsa-web/tailwind.config.js
git commit -m "feat(web): expose gain/loss/accent-brand and font tokens to Tailwind"
```

**🚦 Phase 1 Gate：** 暂停，等用户确认 token 地基（手动换肤可见效果）后再进 Phase 2。

---

# Phase 2 — 切换 UX

> 目标：顶栏家族切换 + 设置页选择器，用户可见可切换。

## Task 2.1: FamilyToggle 组件

**Files:**
- Create: `apps/dsa-web/src/components/theme/FamilyToggle.tsx`
- Test: `apps/dsa-web/src/components/theme/__tests__/FamilyToggle.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
// apps/dsa-web/src/components/theme/__tests__/FamilyToggle.test.tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FamilyThemeProvider, useThemeFamily } from '../FamilyThemeProvider';
import { FamilyToggle } from '../FamilyToggle';

function Probe() {
  const { family } = useThemeFamily();
  return <span data-testid="current">{family}</span>;
}

describe('FamilyToggle', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('lists four families and switches on click', () => {
    render(
      <FamilyThemeProvider>
        <FamilyToggle />
        <Probe />
      </FamilyThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: /主题风格/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /可爱/ }));
    expect(screen.getByTestId('current')).toHaveTextContent('cute');
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/FamilyToggle.test.tsx`
Expected: FAIL（`Cannot find module '../FamilyToggle'`）

- [ ] **Step 3: 实现**

```tsx
// apps/dsa-web/src/components/theme/FamilyToggle.tsx
import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { Check, Palette } from 'lucide-react';
import { cn } from '../../utils/cn';
import { THEME_FAMILIES, type ThemeFamily } from './familyTheme';
import { useThemeFamily } from './FamilyThemeProvider';

const FAMILY_LABELS: Record<ThemeFamily, string> = {
  premium: '高级',
  cute: '可爱',
  minimal: '简约',
  classic: '经典',
};

export const FamilyToggle: React.FC = () => {
  const { family, setFamily } = useThemeFamily();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="主题风格"
        className="inline-flex h-10 items-center gap-2 rounded-xl border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground"
      >
        <Palette className="h-4 w-4" />
        <span>{FAMILY_LABELS[family]}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-36 rounded-xl border border-border/70 bg-popover p-1 shadow-soft-card-strong"
        >
          {THEME_FAMILIES.map((f) => (
            <button
              key={f}
              type="button"
              role="menuitem"
              aria-label={FAMILY_LABELS[f]}
              onClick={() => {
                setFamily(f);
                setOpen(false);
              }}
              className={cn(
                'flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-hover',
                f === family ? 'text-foreground' : 'text-secondary-text'
              )}
            >
              <span>{FAMILY_LABELS[f]}</span>
              {f === family && <Check className="h-4 w-4" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: 运行确认通过**

Run: `cd apps/dsa-web && npx vitest run src/components/theme/__tests__/FamilyToggle.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add apps/dsa-web/src/components/theme/FamilyToggle.tsx apps/dsa-web/src/components/theme/__tests__/FamilyToggle.test.tsx
git commit -m "feat(web): FamilyToggle dropdown for theme family switching"
```

## Task 2.2: 顶栏挂载 FamilyToggle

**Files:**
- Modify: `<ThemeToggle 挂载处>`（用下面命令定位）

- [ ] **Step 1: 定位现有 ThemeToggle 使用点**

Run: `cd apps/dsa-web && grep -rn "<ThemeToggle" src`
Expected: 列出 1–2 处（如 `src/components/layout/SidebarNav.tsx` 或 `ShellHeader.tsx`）。

- [ ] **Step 2: 在每个 ThemeToggle 相邻处加入 FamilyToggle**

在该文件 import 区加 `import { FamilyToggle } from '../theme/FamilyToggle';`（路径按实际目录调整），并在 JSX 中 `<ThemeToggle ... />` 旁渲染 `<FamilyToggle />`（与现有布局容器同级，保持间距类一致）。

- [ ] **Step 3: 构建确认**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add apps/dsa-web/src/components/layout
git commit -m "feat(web): surface FamilyToggle next to ThemeToggle in navigation"
```

## Task 2.3: 设置页主题选择器

**Files:**
- Create: `apps/dsa-web/src/components/settings/ThemeFamilySelector.tsx`
- Test: `apps/dsa-web/src/components/settings/__tests__/ThemeFamilySelector.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
// apps/dsa-web/src/components/settings/__tests__/ThemeFamilySelector.test.tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FamilyThemeProvider } from '../../theme/FamilyThemeProvider';
import { ThemeFamilySelector } from '../ThemeFamilySelector';

describe('ThemeFamilySelector', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders four preview cards and selects on click', () => {
    render(
      <FamilyThemeProvider>
        <ThemeFamilySelector />
      </FamilyThemeProvider>
    );
    expect(screen.getAllByRole('radio')).toHaveLength(4);
    fireEvent.click(screen.getByRole('radio', { name: /简约/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('minimal');
    expect(screen.getByRole('radio', { name: /简约/ })).toHaveAttribute('aria-checked', 'true');
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd apps/dsa-web && npx vitest run src/components/settings/__tests__/ThemeFamilySelector.test.tsx`
Expected: FAIL（模块缺失）

- [ ] **Step 3: 实现**

```tsx
// apps/dsa-web/src/components/settings/ThemeFamilySelector.tsx
import type React from 'react';
import { cn } from '../../utils/cn';
import { THEME_FAMILIES, type ThemeFamily } from '../theme/familyTheme';
import { useThemeFamily } from '../theme/FamilyThemeProvider';

const META: Record<ThemeFamily, { label: string; desc: string; swatch: string }> = {
  premium: { label: '高级', desc: '墨·钢蓝·香槟金，沉稳专业', swatch: 'linear-gradient(135deg,#1e2533,#5b7a99 60%,#b08d57)' },
  cute: { label: '可爱', desc: '草莓奶昔粉，柔和甜美', swatch: 'linear-gradient(135deg,#ff7eb6,#ffd9e8)' },
  minimal: { label: '简约', desc: '纯黑白灰，克制留白', swatch: 'linear-gradient(135deg,#171717,#fafafa)' },
  classic: { label: '经典', desc: '青色科技玻璃拟态', swatch: 'linear-gradient(135deg,#00d4ff,#00a8cc)' },
};

export const ThemeFamilySelector: React.FC = () => {
  const { family, setFamily } = useThemeFamily();
  return (
    <div role="radiogroup" aria-label="主题风格" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {THEME_FAMILIES.map((f) => {
        const selected = f === family;
        return (
          <button
            key={f}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={META[f].label}
            onClick={() => setFamily(f)}
            className={cn(
              'flex flex-col gap-2 rounded-xl border p-3 text-left transition-all',
              selected ? 'border-accent-brand ring-2 ring-accent-brand/40' : 'border-border/70 hover:border-border'
            )}
          >
            <span className="h-12 w-full rounded-lg" style={{ background: META[f].swatch }} />
            <span className="text-sm font-semibold text-foreground">{META[f].label}</span>
            <span className="text-xs text-muted-text">{META[f].desc}</span>
          </button>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 4: 运行确认通过**

Run: `cd apps/dsa-web && npx vitest run src/components/settings/__tests__/ThemeFamilySelector.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add apps/dsa-web/src/components/settings/ThemeFamilySelector.tsx apps/dsa-web/src/components/settings/__tests__/ThemeFamilySelector.test.tsx
git commit -m "feat(web): settings theme family selector with preview cards"
```

## Task 2.4: 设置页接入选择器

**Files:**
- Modify: `apps/dsa-web/src/pages/SettingsPage.tsx`

- [ ] **Step 1: 定位主题/外观相关区块**

Run: `cd apps/dsa-web && grep -n "主题\|外观\|ThemeToggle\|appearance" src/pages/SettingsPage.tsx`
Expected: 找到现有外观/主题设置区（若无则在页面顶部新增一个"外观"分组）。

- [ ] **Step 2: 渲染选择器**

import `import { ThemeFamilySelector } from '../components/settings/ThemeFamilySelector';`，在外观分组内、明暗开关附近渲染：

```tsx
<div className="space-y-2">
  <h3 className="text-sm font-semibold text-foreground">主题风格</h3>
  <ThemeFamilySelector />
</div>
```

- [ ] **Step 3: 构建确认**

Run: `cd apps/dsa-web && npm run build`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add apps/dsa-web/src/pages/SettingsPage.tsx
git commit -m "feat(web): wire theme family selector into settings page"
```

**🚦 Phase 2 Gate：** 暂停，等用户在 UI 上实际切换四套主题确认后再进 Phase 3。

---

# Phase 3 — 组件硬编码迁移（增量、按批）

> 目标：把写死的色值与 Tailwind 字面量收编为 token，让换肤在所有页面真正生效。先审计产出工作清单，再按目录分批。

## Task 3.1: 硬编码色值审计

**Files:**
- Create: `docs/superpowers/reviews/2026-06-02-theme-migration-audit.md`

- [ ] **Step 1: 跑审计扫描**

```bash
cd apps/dsa-web
echo "## 硬编码 hex/rgba" > /tmp/audit.txt
grep -rniE "#[0-9a-f]{3,8}\b|rgba?\(" src --include=*.tsx --include=*.ts --include=*.css | grep -vE "node_modules|__tests__" >> /tmp/audit.txt
echo "## Tailwind 写死调色板（cyan/slate/zinc/purple 等）" >> /tmp/audit.txt
grep -rnoE "(bg|text|border|ring|from|to|via)-(cyan|sky|slate|zinc|neutral|gray|purple|violet|emerald|red|amber)-[0-9]{2,3}" src --include=*.tsx | grep -vE "__tests__" >> /tmp/audit.txt
echo "## dark: 字面量" >> /tmp/audit.txt
grep -rnoE "dark:[a-z-]+-(cyan|slate|zinc|neutral|gray|purple|white|black)[0-9/]*" src --include=*.tsx | grep -vE "__tests__" >> /tmp/audit.txt
wc -l /tmp/audit.txt
```

- [ ] **Step 2: 按目录归类成工作清单**

把 `/tmp/audit.txt` 结果整理进 `docs/superpowers/reviews/2026-06-02-theme-migration-audit.md`，按组件目录分批（建议批次顺序：`layout` → `report` → `dashboard` → `portfolio` → `committee` → `risk` → `decisionTracking` → `quant` → `history` → `settings` → `tasks` → `common` → `StockAutocomplete`），每批列出文件 + 命中行 + 建议映射（如 `#00d4ff`→`hsl(var(--primary))`、`text-cyan-400`→`text-accent-brand-2`、`dark:bg-slate-900`→`bg-surface-2`）。

> 映射对照（统一口径）：
> - 青色/主色 `#00d4ff`/`#00a8cc`/`text-cyan-*` → `--primary` / `text-primary`
> - 紫色点缀 `#a855f7`/`247 84% 66%`/`purple` → `--accent-brand`
> - 涨价红 `--home-price-up`/写死红 → `--gain` / `text-gain`
> - 跌价绿 `--home-price-down`/写死绿 → `--loss` / `text-loss`
> - 卡面/层背景 `dark:bg-slate-900` 等 → `bg-card` / `bg-surface-2`
> - 文本灰 `text-slate-400` 等 → `text-muted-text` / `text-secondary-text`
> - 白底叠加 `rgba(255,255,255,0.05)` → `hsl(var(--foreground) / 0.05)`

- [ ] **Step 3: 提交审计**

```bash
git add docs/superpowers/reviews/2026-06-02-theme-migration-audit.md
git commit -m "docs(review): hardcoded color audit for theme migration"
```

## Task 3.x（重复模板）: 单批目录 token 化

> 对审计清单里的**每个批次**重复以下步骤。N = 批次序号，DIR = 该批目录（如 `report`）。

- [ ] **Step 1: 列出该批命中**

Run: `cd apps/dsa-web && grep -rniE "#[0-9a-f]{3,8}\b|rgba?\(|(bg|text|border)-(cyan|slate|zinc|purple|emerald|red|amber)-[0-9]{2,3}" src/components/DIR --include=*.tsx | grep -v __tests__`

- [ ] **Step 2: 按映射对照逐个替换**

把命中项按 Task 3.1 的映射口径替换为 token 工具类 / `hsl(var(--*))`。**只动颜色相关属性，不动结构、props、逻辑**。涨跌语义务必映射到 `--gain`/`--loss`（同时收编该批里残留的 `--home-price-up/down` 等旧涨跌色引用——**仅颜色层，后端方向词表不动**，见 [[repo-candidate-direction-vocab-drift]]）。

- [ ] **Step 3: 四套 × 明暗目视走查该批组件**

Run: `cd apps/dsa-web && npm run build && npm run dev`
依次在 DevTools 设 `data-theme` = premium/cute/minimal/classic，各自切明暗，确认该批组件颜色随主题变化、对比度可读、无残留青色。

- [ ] **Step 4: 跑受影响单测（若该目录有）**

Run: `cd apps/dsa-web && npx vitest run src/components/DIR`
Expected: PASS（纯颜色替换不应改变断言；若有断言写死 class 名需同步更新）。

- [ ] **Step 5: lint + 构建**

Run: `cd apps/dsa-web && npm run lint && npm run build`
Expected: 通过。

- [ ] **Step 6: 提交该批**

```bash
git add apps/dsa-web/src/components/DIR
git commit -m "refactor(web): tokenize DIR colors for multi-theme support"
```

**🚦 Phase 3 Gate：** 每批可单独让用户确认；全部批次完成后整体确认再进 Phase 4。

---

# Phase 4 — 可爱风专属点缀（C/D/E/F）

## Task 4.1: 贴纸徽章 + 按钮微弹跳（C/E，纯 CSS）

**Files:**
- Modify: `apps/dsa-web/src/index.css`

- [ ] **Step 1: 追加可爱风专属样式**

在 index.css 末尾的 `@layer components` 之外（或合适处）追加：

```css
/* ===== 可爱风专属点缀（仅 data-theme=cute 生效） ===== */
[data-theme="cute"] .badge,
[data-theme="cute"] .home-accent-chip {
  box-shadow: 0 3px 0 hsl(var(--accent-brand) / 0.35), 0 5px 10px hsl(var(--primary) / 0.25);
}
[data-theme="cute"] button:hover:not(:disabled) {
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
[data-theme="cute"] button.cute-bounce:hover:not(:disabled) {
  transform: scale(1.06) translateY(-2px);
}
```

> 说明：弹跳作用域用 `.cute-bounce` 显式类，避免污染所有按钮；主行动按钮在 Phase 3/4 加该类。贴纸投影挂在既有 `.badge` 类上，自动覆盖已 token 化的徽章。

- [ ] **Step 2: 构建 + 可爱风目视**

Run: `cd apps/dsa-web && npm run build && npm run dev`（data-theme=cute）
Expected: 徽章有立体投影；带 `.cute-bounce` 的按钮 hover 放大上浮；其他主题不受影响。

- [ ] **Step 3: 提交**

```bash
git add apps/dsa-web/src/index.css
git commit -m "feat(web): cute theme sticker badges and button bounce"
```

## Task 4.2: 标题圆体（F）

**Files:**
- Modify: `apps/dsa-web/index.html`（引入字体）+ 相关标题组件改用 `font-display`

- [ ] **Step 1: 引入 Quicksand/Fraunces 字体**

在 `index.html` `<head>` 加（用 `display=swap` 不阻塞首屏；字体仅在对应家族用到）：

```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@500;700&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap" rel="stylesheet" />
```

> 未决项（spec §12）：若不想依赖 CDN，改为本地 `@font-face` 打包；二选一，构建期定。

- [ ] **Step 2: 页面主标题/区块名改用 font-display**

Run: `cd apps/dsa-web && grep -rn "title-gradient\|text-2xl font-bold\|text-xl font-semibold" src/components/layout src/pages | head`
对页面级标题/区块标题元素加 `font-display` 工具类（**不要加在数字、价格、表格单元上**）。

- [ ] **Step 3: 构建 + 四主题目视**

Run: `cd apps/dsa-web && npm run build && npm run dev`
Expected: 可爱风标题为圆体、高级风标题为衬线、简约/经典为无衬线；数字不受影响。

- [ ] **Step 4: 提交**

```bash
git add apps/dsa-web/index.html apps/dsa-web/src
git commit -m "feat(web): wire display fonts (Quicksand/Fraunces) per family"
```

## Task 4.3: 可爱风空状态 + 心跳 loading（D，唯一组件级分支）

**Files:**
- Modify: 共享空状态/加载组件（用命令定位）
- Test: 对应 `__tests__`

- [ ] **Step 1: 定位共享空状态/loading 组件**

Run: `cd apps/dsa-web && grep -rln "EmptyState\|暂无\|还没有\|开始分析\|加载中\|Loading" src/components/common src/components | head`
Expected: 找到 1–2 个共享展示组件（如 `common/EmptyState.tsx`、`common/LoadingSpinner.tsx`）。

- [ ] **Step 2: 写失败测试（家族分支渲染）**

```tsx
// 在对应 __tests__ 下，示例针对 EmptyState
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FamilyThemeProvider } from '../../theme/FamilyThemeProvider';
import { EmptyState } from '../EmptyState';

describe('EmptyState cute variant', () => {
  it('shows mascot when family is cute', () => {
    window.localStorage.setItem('dsa-theme-family', 'cute');
    render(<FamilyThemeProvider><EmptyState message="还没有分析记录" /></FamilyThemeProvider>);
    expect(screen.getByText('🍡')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2b: 运行确认失败**

Run: `cd apps/dsa-web && npx vitest run src/components/common/__tests__/EmptyState.test.tsx`
Expected: FAIL（🍡 未渲染）

- [ ] **Step 3: 在组件里加 family 分支**

读 `useThemeFamily()`，`family === 'cute'` 时在原有内容上方渲染 `<div aria-hidden>🍡</div>` 与 `💗 💗 💗`（loading 组件同理换成心跳点）。其余主题维持原样。**这是 spec 允许的唯一组件级分支**，仅限这 1–2 个共享展示组件。

- [ ] **Step 4: 运行确认通过 + 构建**

Run: `cd apps/dsa-web && npx vitest run src/components/common && npm run build`
Expected: PASS + 构建成功。

- [ ] **Step 5: 提交**

```bash
git add apps/dsa-web/src/components/common
git commit -m "feat(web): cute empty-state mascot and heart loading variant"
```

**🚦 Phase 4 Gate：** 暂停确认可爱风点缀。

---

# Phase 5 — 收尾

## Task 5.1: 四套 × 明暗逐屏走查 + 对比度

- [ ] **Step 1: 逐屏走查清单**

Run: `cd apps/dsa-web && npm run build && npm run dev`
对主要页面（首页/报告页/持仓/委员会/设置/登录/历史）逐一在 4 家族 × 明暗下截图核对：无残留青色硬编码、涨跌色正确、可读。

- [ ] **Step 2: 对比度检查**

用浏览器 DevTools 或 axe 扩展，对每套主题的正文/次要文字/muted 文字与背景对比度过 WCAG AA（正文 ≥ 4.5:1）。重点：可爱风浅色 `--muted-text` on `--background`、简约暗色 `--muted-foreground`。不达标项微调该 token 的 L 值。

- [ ] **Step 3: 修正并提交**

```bash
git add apps/dsa-web/src/index.css
git commit -m "fix(web): adjust theme tokens for WCAG AA contrast"
```

## Task 5.2: 文档 + CHANGELOG

**Files:**
- Modify: `docs/CHANGELOG.md`、相关主题文档（如 `docs/full-guide.md` 增"主题切换"小节）

- [ ] **Step 1: CHANGELOG（扁平格式，追加到 `[Unreleased]` 末尾）**

```
- [新功能] Web 端多主题视觉系统：新增可爱 / 简约 / 高级三套风格 + 保留经典，每套含浅/暗两模式，顶栏与设置页可切换，localStorage 记忆，默认高级、明暗跟随系统。token 驱动（data-theme 家族 × .dark 模式），组件零逻辑改动。
```

- [ ] **Step 2: 用户文档补"主题切换"小节**

在 `docs/full-guide.md` 增说明：四套主题、切换入口（顶栏 + 设置页）、记忆方式、默认行为。

- [ ] **Step 3: 提交**

```bash
git add docs/CHANGELOG.md docs/full-guide.md
git commit -m "docs: document multi-theme switching"
```

**🚦 Phase 5 Gate：** 全部完成，整体验收，决定是否开 PR 合入 main。

---

## 自查（Self-Review）记录

- **Spec 覆盖**：架构（Task 1.1-1.4）、token 契约 + 配色（1.5-1.6）、性格 token（1.5 含 radius/font）、切换 UX（2.1-2.4）、迁移（3.x）、可爱 C/D/E/F（4.1-4.3）、a11y + 文档（5.1-5.2）。经典保留 = 不改 :root/.dark 既有值，仅追加新语义 token。✅
- **占位符**：Phase 1/2/4 均含完整代码与测试；Phase 3 为审计驱动的重复模板（DIR 占位是有意的批次变量，非内容缺失）。✅
- **类型一致**：`ThemeFamily`、`useThemeFamily`、`setFamily`、`FAMILY_STORAGE_KEY`、`applyFamilyToDocument` 跨任务命名一致。✅
- **已知前提**：jsdom localStorage 依赖现有 `setupTests.ts` MemoryStorage polyfill；CI 不跑 vitest，需本地兜底；桌面端经 `static/` 重建自动继承。
