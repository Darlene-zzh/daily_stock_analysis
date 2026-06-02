# 多主题视觉重设 — 设计文档

> **状态**：设计已确认（2026-06-02 brainstorming 产出），待转 implementation plan。
> **范围**：仅 `apps/dsa-web/` 前端视觉层 + `index.css` + `tailwind.config.js`。不改组件逻辑/props、不改后端、不改方向词表。

## 1. 目标

把 Web 前端从当前**单一青色科技风**升级为**可切换的多主题系统**：3 套全新风格 + 保留现状作为第 4 套，每套都有浅色与暗色两种模式（共 4 家族 × 2 模式 = 8 种组合）。

- **可爱风**（草莓奶昔）
- **简约风**（纯黑白灰）
- **高级 / 中性风**（墨 · 钢蓝 · 香槟金）
- **经典**（现状青色科技风，保留归档，不重做）

新模块上线后应**零成本继承**全部主题。

## 2. 设计原则

1. **Token 驱动换肤（方案 A）**：组件只读语义 CSS 变量，不出现具体色值。换主题 = 换变量值。
2. **双轴正交**：家族（`data-theme`）与模式（`.dark`）互不干扰。
3. **可爱集中在非数据区**：数据/数字/表格保持专业可读，萌元素只加在空状态、加载、按钮、徽章、字体等非数据表面。
4. **稳定优先**：增量迁移，每批可独立验证；老报告/老组件无 token 时优雅回退。
5. **新模块免费继承**：地基建好后，新页面只要用 token 就自动支持 4 套主题。

## 3. 架构：双轴 token 系统

### 3.1 轴

- **模式轴（明/暗）**：维持现有 `next-themes`，`attribute="class"` 切 `.dark`，`enableSystem`，Tailwind `darkMode:['class']` 不变。
- **家族轴（4 套）**：`<html data-theme="...">`，由新增 `FamilyThemeProvider` 管理，持久化到 `localStorage`（键：`dsa-theme-family`）。

### 3.2 CSS 结构

复用现有 token 底座，最小化对"经典"值的改动：

```css
:root            { /* 经典 · 浅（现有值，基本不动，作为无 data-theme 时的回退） */ }
.dark            { /* 经典 · 暗（现有值） */ }

[data-theme="premium"]        { /* 高级 · 浅 */ }
[data-theme="premium"].dark   { /* 高级 · 暗 */ }
[data-theme="cute"]           { /* 可爱 · 浅 */ }
[data-theme="cute"].dark      { /* 可爱 · 暗 */ }
[data-theme="minimal"]        { /* 简约 · 浅 */ }
[data-theme="minimal"].dark   { /* 简约 · 暗 */ }
```

- 默认家族 = `premium`，由 Provider 在首次访问时写入 `data-theme="premium"`。
- 无 `data-theme` 时回退到 `:root`（经典），保证任何异常下都有可用样式。

### 3.3 语义 Token 契约（每套主题必须填满）

| 组 | Token | 说明 |
|---|---|---|
| 基底 | `--background` / `--surface-1/2/3` | 页底、卡面、悬浮、嵌入层 |
| 文字 | `--foreground` / `--secondary-text` / `--muted-text` | |
| 描边 | `--border` / `--border-subtle` / `--border-hover` / `--border-selected` | |
| 品牌 | `--primary` / `--primary-foreground` / `--accent` / `--accent-2` | `--accent-2` 给高级风的金 |
| 金融语义 | `--gain` / `--loss` / `--gain-soft` / `--loss-soft` | **涨跌色每套独立定义**，默认红涨绿跌 |
| 状态 | `--success` / `--warning` / `--danger` / `--info` | |
| 效果 | `--shadow-card` / `--shadow-card-strong` / `--glow` | |

> 规则：组件只准读这些语义 token，禁止再出现具体色值。

### 3.4 性格差异化 Token

| Token | 可爱 | 简约 | 高级 | 经典 |
|---|---|---|---|---|
| `--radius`（圆角档） | 大 16–18px | 小 8px | 中 10px | 中大 14px |
| `--font-sans`（正文） | 圆体 Quicksand/Nunito | Inter/Geist | Inter | 现状 |
| `--font-display`（标题） | 圆体（更胖） | = 正文 | 衬线 Fraunces/Georgia | 现状 |
| `--deco`（装饰） | 贴纸投影/🎀/⭐ | 无 | 顶部金线 / ★精选 | 青色辉光 |
| `--ring-style`（选中态） | 粉描边 | 黑/白细框 | 钢蓝 + 金 | 青辉光 |

字体用 `font-display: swap` + 系统字体回退，不阻塞首屏。

## 4. 锁定配色

> 涨 = gain（默认红），跌 = loss（默认绿），符合 A 股惯例。

### 4.1 可爱风 · 草莓奶昔

| | 浅色 | 暗色 |
|---|---|---|
| background | `#fff0f6` | `#15171d`（冷石板灰） |
| surface | `#ffffff` | `#222631`（卡面渐变 `#242833`→`#1e222c`） |
| border | `#ffd9e8` / `#ffd1e3` | `#333a48` |
| primary | `#ff7eb6` | `#ff8fc2` |
| accent（深玫） | `#e3588f` | `#ffa9d2` |
| foreground | `#5b3a4a` | `#eef2f8` |
| muted | `#9a7c89` | `#8d96a6` |
| gain（涨） | `#ff4d7d` | `#ff6f9c` |
| loss（跌·叶绿） | `#4fb87f` | `#5fc98e` |

### 4.2 简约风 · 纯黑白灰

| | 浅色 | 暗色 |
|---|---|---|
| background | `#fafafa` | `#0a0a0a` |
| surface | `#ffffff` | `#161616` |
| border | `#e5e5e5` | `#262626` |
| foreground | `#171717` | `#fafafa` |
| muted | `#737373` | `#a1a1aa` |
| accent | 单色（= foreground 墨/白），无彩色点缀 | 同 |
| gain（涨·克制红） | `#dc2626` | `#f87171` |
| loss（跌·克制绿） | `#16a34a` | `#4ade80` |

### 4.3 高级 / 中性风 · 墨 · 钢蓝 · 香槟金

| | 浅色 | 暗色 |
|---|---|---|
| background | `#f4f5f7` | `#0d1018` |
| surface | `#ffffff` | `#161b26`（渐变 →`#11151e`） |
| border | `#e2e4e8` | `#232a38` |
| primary（墨） | `#1e2533` | `#eef1f6`（暗色下文字/主体反转） |
| foreground | `#1e2533` | `#eef1f6` |
| muted | `#9499a3` | `#6b7280` |
| accent（钢蓝·主点缀） | `#5b7a99` | `#7d9bba` |
| accent-2（香槟金·点睛） | `#b08d57` | `#d8b878` / `#9c7838` |
| gain（涨·绛红） | `#c0392b` | `#f0635a` |
| loss（跌·墨绿） | `#2e7d5b` | `#4cc38a` |

- **金属用法**：钢蓝做主力（描边、次按钮、选中态）；香槟金克制点睛（卡片顶部细金线、`★ 精选` 标记、关键强调）。
- **字体**：衬线标题（Fraunces/Georgia）+ 无衬线正文。

### 4.4 经典 · 青色科技（保留）

沿用现有 `:root` / `.dark` 的青/紫玻璃拟态值，不重做。

## 5. 可爱风专属增强（已选 C / D / E / F）

| 项 | 实现方式 | 是否动组件 |
|---|---|---|
| **C 贴纸感 puffy 徽章** | `[data-theme="cute"]` 选择器给现有 badge/button 类加立体投影 | 否，纯 CSS |
| **E 按钮 hover 微弹跳** | `[data-theme="cute"]` 给按钮加 `transform: scale(1.06) translateY(-2px)` transition | 否，纯 CSS |
| **F 标题圆体** | `--font-display` 在可爱风指向更胖圆体，仅用于标题/区块名，**不用于数字** | 否，token |
| **D 可爱空状态 + 心跳 loading** | 共享 EmptyState / Loading 组件读 `useThemeFamily()==='cute'` 渲染 🍡 吉祥物 + 💗 loading | 是，**唯一允许的组件级分支**，限于 1–2 个共享展示组件 |

- 未选：A 背景肌理、B 卡片渐变顶条 —— 跳过。

## 6. 切换 UX

- **Provider**：`FamilyThemeProvider` 包在 `next-themes` 外层，写 `data-theme` + localStorage，导出 `useThemeFamily()` / `setFamily()`。
- **顶栏快捷入口**：现有 `ThemeToggle`（明暗）旁加家族下拉（经典/可爱/简约/高级，小图标）。
- **设置页完整选择器**：4 张主题预览卡（缩略图 + 名称），点选即时生效；明暗开关同处。
- **首次访问**：家族 = 高级（premium），明暗 = 跟随系统（`enableSystem`）。
- **防闪（FOUC）**：在 `<head>` 内联脚本里，与 `.dark` 一样尽早写上 `data-theme`，避免首屏闪烁。

## 7. 组件迁移范围（核心工作量）

- 扫描替换硬编码色值：`#00d4ff` 系青色渐变、`rgba(0,212,255,…)` 发光、`rgba(255,255,255,…)` 等 → `var(--*)` token。
- 收编 Tailwind 字面量：`dark:bg-slate-900`、`text-cyan-400` 等 → 语义工具类（`bg-surface-2` / `text-gain` …）。
- 涨跌色收口：现有 `--home-price-up/down`、`--home-strategy-*` 等多处定义统一并入 `--gain/--loss`，4 套各自赋值。**只动颜色层，不改后端方向词表**（见 [[repo-candidate-direction-vocab-drift]]）。
- 接入性格 token（`--radius` / `--font-display` / 贴纸投影 / 弹跳）。
- **边界**：只动 `apps/dsa-web/` 样式 + `index.css` + `tailwind.config.js`；不改组件逻辑/props、不动后端。

## 8. 分阶段实施

1. **Phase 1 — Token 地基**：语义契约 + 性格 token，`index.css` 写全 4 家族 × 明暗值；建 `FamilyThemeProvider`（暂不接 UI）。零可见变化、可独立验证。
2. **Phase 2 — 切换 UX**：顶栏入口 + 设置页选择器 + 防闪脚本。能切换，但部分硬编码组件尚未全跟随。
3. **Phase 3 — 组件迁移**：按目录分批 token 化（report / dashboard / portfolio / committee / settings / layout …），每批一个小 PR。大头，增量合入。
4. **Phase 4 — 可爱风点缀**：C/D/E/F 接入。
5. **Phase 5 — 收尾**：4 套 × 明暗逐屏走查、对比度无障碍检查、文档 + `docs/CHANGELOG.md`。

> 每个 Phase 由用户 gate（逐阶段确认提交，见 [[feedback-phase-commit-gating]]）。

## 9. 验证

- 每批：`cd apps/dsa-web && npm ci && npm run lint && npm run build`；`npx vitest run` 本地兜底（**CI 不跑 vitest**，见 [[repo-web-test-infra-gaps]]）。
- 改完前端必须 `npm run build` 才能刷掉浏览器旧 bundle（[[repo-static-bundle-hash-cache]]）。
- 桌面端是 Electron 壳直接 loadURL 后端服务的 web 产物，web 重建 `static/` 后桌面端自动跟随（[[repo-desktop-is-electron-shell]]），无需单独改桌面端。
- 无障碍：8 种组合逐一过 WCAG 对比度（尤其可爱风浅色 + 数据文字、简约风灰字）。

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 硬编码色值漏迁 → 某些元素不换肤 | grep 审计 + 每屏逐一走查；分批可控 |
| 某些组合对比度不达标 | Phase 5 WCAG 检查，必要时微调该组合的 token |
| 字体加载 FOUC | `font-display: swap` + 系统字体回退 |
| `data-theme` + `.dark` 双重首屏闪烁 | `<head>` 内联脚本尽早写两者 |
| 涨跌色收口波及后端方向语义 | 只改颜色层，后端方向词表完全不动 |
| 组件级分支蔓延 | 仅 D（空状态/loading）允许 1–2 个共享组件读 family，其余一律 CSS/token |

## 11. 非目标（YAGNI）

- 不做布局/结构性改版（卡片排布、信息架构不变）。
- 不为每套主题分叉组件（除 D 的极小例外）。
- 不改后端、API、Schema、方向词表。
- 不引入主题市场/自定义配色等扩展能力。

## 12. 未决（实现期确认）

- 具体字体来源（本地打包 vs CDN）与体积取舍，Phase 1 时定。
- 顶栏家族切换控件的具体形态（图标下拉 vs 分段控件），Phase 2 出 UI 时定。
