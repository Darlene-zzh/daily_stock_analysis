# LLMChannelEditor 巨型组件拆解 — 设计文档

- **Date**: 2026-05-19
- **Scope**: `apps/dsa-web/src/components/settings/LLMChannelEditor.tsx`（仅此一个文件）
- **Driver**: react-doctor 体检后 14 条 warning 集中于此，其中 2 条 `no-giant-component` + 1 条 `prefer-useReducer` + 1 条 `no-cascading-set-state` 形成 Architecture/State 重灾区。本设计针对此文件做 **Medium+** 级别重构（架构拆解 + ChannelRow 内部子拆 + a11y + perf）。
- **Out of scope**:
  - ChatPage.tsx、PortfolioPage.tsx 的巨型组件问题（另行专题）
  - `useReducer` 重写（Deep 级，未来再议）
  - **主 `LLMChannelEditor` 组件本身的子拆**（760 行函数体）—— 主 editor 的 `no-giant-component` 警告会**留到 Deep 级专题**，本次只拆 `ChannelRow`

## 1. 现状

```
src/components/settings/LLMChannelEditor.tsx   1803 行
  ├ ChannelConfig / ChannelTestState / ChannelDiscoveryState 等接口     (line 72-136)
  ├ ChannelRow 组件                                                      (line 138-540)
  ├ 31 个纯函数 helper（parser / normalizer / formatter / sanitizer 等）  (line 542-1042)
  ├ LLMChannelEditor 主组件 — 12 useState + 多 ref + sync useEffect      (line 1044-1803)
```

**react-doctor 警告分布**（基于 2026-05-19 体检）：

| 行 | 规则 | 类别 |
|---|---|---|
| 138 | no-giant-component | Architecture |
| 277 | label-has-associated-control | Accessibility |
| 386 | label-has-associated-control | Accessibility |
| 597 | js-flatmap-filter | Performance |
| 962 | js-flatmap-filter | Performance |
| 1005 | js-set-map-lookups | Performance |
| 1016 | js-set-map-lookups | Performance |
| 1044 | no-giant-component | Architecture |
| 1050 | prefer-useReducer | State & Effects |
| 1091 | no-cascading-set-state | State & Effects |
| 1413 | async-defer-await | Performance |
| 1491 | async-defer-await | Performance |
| 1659 | label-has-associated-control | Accessibility |
| 1712 | label-has-associated-control | Accessibility |

**测试覆盖**：`src/components/settings/__tests__/LLMChannelEditor.test.tsx`，1460 行，**37 个 vitest 测试，截至 2026-05-19 全部通过**。

## 2. 目标

| 维度 | 目标 |
|---|---|
| **Warnings** | 文件警告从 14 → 3-4（剩 1 个主 editor 的 `no-giant-component` + `prefer-useReducer` + `no-cascading-set-state`，可能 0-1 个 async-defer-await 留 disable-comment） |
| **架构** | 主文件从 1803 行 → ~720 行；ChannelRow 从 403 行 → ~200 行；3 个 sub-panel 各 50-80 行 |
| **行为** | 零业务逻辑变化，37 个测试全部继续通过 |
| **风险** | 每步 commit 独立 build-green + test-green，可逐 commit 回滚 |

**不做的事**（Out of scope）：
- **主 editor 的 760 行函数体子拆**（留 Deep）—— 该 warning 保留
- 主 editor 的 12 useState 合并到 useReducer（Deep 级）
- ChannelRow 的 4 个 props 关联状态（`testState`/`discoveryState`/`capabilityState`/`expanded`）从父组件下推到自身（state 形态变化，留 Deep）
- 重写 sync useEffect（line 1091 cascading setState 问题，留 Deep）
- 任何 UI/视觉变化

**关键设计判断**：`no-giant-component` 看的是组件函数体行数（不是文件行数）。所以 ChannelRow 抽到单独文件**不会**降低它自己的行数 —— 必须实际拆出 sub-component 才能让 ChannelRow 函数体降到 300 行以下。本次只对 ChannelRow 做这层拆，主 editor 同样的问题留 Deep。

## 3. 架构

### 文件布局

```
src/components/settings/LLMChannelEditor/
├── LLMChannelEditor.tsx           # 主组件，~720 行函数体（从 1803 行文件、760 行函数体降下来）
├── ChannelRow.tsx                 # 编排父组件，~200 行（从 403 行降下来）
├── ChannelTestPanel.tsx           # 子组件：连接测试结果展示，~50 行
├── ChannelDiscoveryPanel.tsx      # 子组件：模型发现 + 可选模型列表，~80 行（含 line 386 group label 修复）
├── ChannelCapabilityPanel.tsx     # 子组件：运行时能力检测 + 结果列表，~70 行
├── types.ts                       # 接口 + UI option 常量，~95 行
├── utils.ts                       # 31 个纯 helper + 9 个查找表常量，~480 行
├── index.ts                       # 单行 re-export：`export { LLMChannelEditor } from './LLMChannelEditor';`
└── __tests__/
    └── LLMChannelEditor.test.tsx  # 从 settings/__tests__/ 整体迁入
```

**对齐已有约定**：与 `src/components/StockAutocomplete/` 同形态（folder + index.ts 桥接 + 同名主文件 + 兄弟测试目录）。

**为何需要 index.ts**：现有 `src/components/settings/index.ts:1` 写的是 `export * from './LLMChannelEditor';`。删除旧 `LLMChannelEditor.tsx` 之后，TS 模块解析对 `'./LLMChannelEditor'` 会去找 `'./LLMChannelEditor/index.ts'`（TS 不会自动把 `'./X'` 当成 `'./X/X.tsx'`）。这个 1 行的 index.ts 就是给 settings 桶 barrel 续命用的，**外部 importer 仍然走直接路径**避免触发 no-barrel-import 警告。

### 外部调用方影响

| 文件 | 当前 | 目标 |
|---|---|---|
| `src/components/settings/index.ts:1` | `export * from './LLMChannelEditor';` | 不变（依赖新建的 `LLMChannelEditor/index.ts` 解析 folder import） |
| `src/pages/SettingsPage.tsx:14` | `import { LLMChannelEditor } from '../components/settings/LLMChannelEditor';` | `import { LLMChannelEditor } from '../components/settings/LLMChannelEditor/LLMChannelEditor';` — 直接路径避免 barrel 警告 |
| `__tests__/LLMChannelEditor.test.tsx:4` | `from '../LLMChannelEditor';` | `from '../LLMChannelEditor';`（从新位置看，相对路径恰好不变） |

### 模块切分明细

#### `types.ts` (~95 行)

**接口**（直接搬运）：
- `ChannelConfig`、`ChannelTestState`、`ChannelDiscoveryState`、`ChannelCapabilityState`、`RuntimeConfig`、`LLMChannelEditorProps`、`ChannelRowProps`、`ParsedModelRef`

**UI option/label 常量**（与接口紧耦合的展示数据）：
- `PROTOCOL_OPTIONS`、`RUNTIME_CAPABILITY_OPTIONS`、`CAPABILITY_STATUS_LABELS`

#### `utils.ts` (~480 行)

**31 个纯函数**（按现文件出现顺序）：
- `normalizeProtocol`、`inferProtocol`、`parseEnabled`、`splitModels`、`parseModelRef`、`getModelComparisonKey`、`areModelsEquivalent`、`toggleModelSelection`、`normalizeModelForRuntime`、`resolveModelPreview`、`buildModelOptions`
- `getLlmStageLabel`、`getLlmErrorCodeLabel`、`getLlmTroubleshootingHint`、`buildLlmTestHint`、`buildLlmFailureText`、`getCapabilityResultVariant`、`summarizeCapabilityResults`、`getFirstCapabilityHint`
- `getRuntimeProvider`、`usesDirectEnvProvider`、`hasLegacyRuntimeSource`、`isRuntimeModelAvailable`、`sanitizeRuntimeConfigForSave`、`runtimeConfigsAreEqual`、`resolveTemperatureFromItems`、`normalizeAgentPrimaryModel`
- `parseRuntimeConfigFromItems`、`parseChannelsFromItems`、`channelsToUpdateItems`、`channelsAreEqual`

**它们依赖的查找表常量**：
- `KNOWN_MODEL_PREFIXES`、`FALSEY_VALUES`、`PROTOCOL_ALIASES`、`LLM_STAGE_LABELS`、`LLM_ERROR_LABELS`、`LLM_TROUBLESHOOTING_HINTS`、`LLM_REASON_HINTS`、`MANAGED_PROVIDERS`、`LEGACY_PROVIDER_KEYS`

#### `ChannelRow.tsx` (~200 行，从 403 行降下来)

ChannelRow 作为**编排父组件**保留：
- 渲染折叠/展开切换
- 渲染顶部信息行（name / protocol / baseUrl / apiKey / models 输入）
- 渲染 3 个子 panel：`<ChannelTestPanel>` / `<ChannelDiscoveryPanel>` / `<ChannelCapabilityPanel>`
- 处理 collapsed/expanded UI 状态切换
- 把 props 透传给 3 个 panel

**移出去的部分** —— 见下面 3 个 sub-panel 文件。

#### `ChannelTestPanel.tsx`（~50 行，新建）

接收 props：
- `testState?: ChannelTestState`
- `busy: boolean`
- `onTest: () => void`

渲染：测试按钮 + 加载态 + 成功/失败提示 + troubleshooting hint 展示。

#### `ChannelDiscoveryPanel.tsx`（~80 行，新建）

接收 props：
- `channel: ChannelConfig`
- `discoveryState?: ChannelDiscoveryState`
- `busy: boolean`
- `onDiscoverModels: () => void`
- `onUpdate: (index, field, value) => void`
- `index: number`

渲染：模型发现按钮 + 加载态 + 错误提示 + **可选模型 checkbox 列表（含 line 386 group label 用 fieldset/legend 修复）**

#### `ChannelCapabilityPanel.tsx`（~70 行，新建）

接收 props：
- `channel: ChannelConfig`
- `capabilityState?: ChannelCapabilityState`
- `busy: boolean`
- `onToggleCapability: (capability) => void`
- `onCheckCapabilities: () => void`

渲染：能力勾选 checkbox + 检测按钮 + 加载态 + 每项 capability 检测结果。

**所有 3 个 sub-panel 都保持 named export，无独立测试**（37 个测试覆盖整个 ChannelRow 行为，sub-panel 通过 ChannelRow 集成验证）。

#### `LLMChannelEditor.tsx` 主组件 (~720 行)

什么留下：
- 主组件定义（原 line 1044-1803）
- 12 个 useState、所有 refs、sync useEffect、所有 useMemo —— **全部不动**

什么变：
- imports 调整为从 `./types`、`./utils`、`./ChannelRow` 导入
- 删除内联的接口/helper/ChannelRow 定义

### 不变量与保护机制

| 不变量 | 保护机制 |
|---|---|
| ChannelRow props 形状不变 | types.ts 集中导出，跨模块编译期校验 |
| 37 个测试断言全过 | 每个 commit 跑 `npm test --run LLMChannelEditor.test.tsx` |
| 外部 import 不破坏 | tsc 编译期校验；SettingsPage 路径显式更新 |
| `npm run lint` + `npm run build` 绿 | 每个 commit 后跑完整套 |
| 视觉无变化 | 不动 JSX 结构、不动 className |

## 4. Medium+ 周边优化

精读 8 处 lint 位置后，区分**真实修复**和**误报**。所有行号引用 **2026-05-19 当前文件状态**（D1 架构搬迁 + D2 ChannelRow 子拆后行号会变化，但概念位置不变）：

### A11y · 4 处 label-has-associated-control（全部真实可修）

| 行 | 现状 | 修法 |
|---|---|---|
| 277 | `<label>协议</label>` + `<Select>`（兄弟） | 加 `id` 给 Select、`htmlFor` 给 label（`useId()` 生成 id） |
| 386 | `<label>可选模型（可多选）</label>` + 内嵌 checkbox 列表 | 改用 `<fieldset><legend>可选模型（可多选）</legend>...</fieldset>` 包整组（语义最准）；用 Tailwind `border-0 m-0 p-0` 抹掉 `<fieldset>` 默认边框 |
| 1659 | `<label>Temperature</label>` + `<input type="range">`（兄弟） | 加 `id` + `htmlFor` |
| 1712 | `<label>备选模型</label>` + 内嵌 checkbox 列表 | 同 386，用 `<fieldset><legend>` 包整组 |

### Perf · 2 处 js-flatmap-filter（全部真实可修）

| 行 | 现状 | 修法 |
|---|---|---|
| 597 (`splitModels`) | `.split(',').map(trim).filter(Boolean)` | `.split(',').flatMap(e => { const t = e.trim(); return t ? [t] : []; })` |
| 962 (`parseChannelsFromItems`) | 同样模式，且就是 `splitModels` 的等价手写 | 直接调用 `splitModels(itemMap.get('LLM_CHANNELS') || '')`，消除重复逻辑 |

### Perf · 2 处 js-set-map-lookups（1 真 + 1 误报）

| 行 | 现状 | 判定 | 处理 |
|---|---|---|---|
| 1005 | `channel.apiKey.includes(',')` | **误报** — `apiKey` 是 string，是 `String.prototype.includes`，不是 array lookup | inline `// eslint-disable-next-line js-set-map-lookups -- String.includes, not array lookup` |
| 1016 | `activeNames.includes(upperName)` 在 `for-of previousChannelNames` 内 | **真实 O(n²)** | 循环外 `const activeNamesSet = new Set(activeNames);`，循环内 `activeNamesSet.has(...)` |

### Perf · 2 处 async-defer-await（疑似误报，实施时再确认）

| 行 | 现状 | 初步判定 | 处理 |
|---|---|---|---|
| 1413 (`handleDiscoverModels`) | 函数无 early return，先 sync setState（loading 转场）再 await | lint 说的 "early-return that doesn't use the awaited value" 不存在；setState 在 await 之前是 React 加载态标准写法 | 实施时再细查源码看是否有遗漏的 guard；如确认误报，inline disable + reason |
| 1491 (`handleCapabilityCheck`) | 第 1472 行已有 `if (selected.length === 0) return;` early return；await 在 1491 已经在 guard 之后 | lint 似乎没识别到这是 fast-path | 同上 |

**实施透明承诺**：如果实施时发现「误报」其实是我误判，会调整为真实修复（移动 await 位置）并更新本设计。最终 commit 信息会反映实际选择。

### 警告消耗汇总

| 来源 | 真实修复 | disable 注释「消耗」 | 合计可见 |
|---|---|---|---|
| ChannelRow 内部拆 3 个 sub-panel，ChannelRow 函数体从 403 行降到 ~200 行（line 138 警告归零） | 1 | 0 | 1 |
| 主 LLMChannelEditor 函数体 760 行**不动**（line 1044 警告**保留**） | 0 | 0 | 0 |
| 4 label-has-associated-control | 4 | 0 | 4 |
| 2 js-flatmap-filter | 2 | 0 | 2 |
| 1 真 set-map + 1 误报 | 1 | 1 | 2 |
| 0-2 真 async-defer-await + 2-0 误报 | 0-2 | 0-2 | 2 |
| **总计** | **8-10** | **1-3** | **11** |

**Lint 输出可见**：14 → 3（剩 line 1044 `no-giant-component` + `prefer-useReducer` + `no-cascading-set-state`），全部明确留给 Deep 级专题。

## 5. 实施节奏（4 个 commit）

### D1 — 纯架构搬迁（零 sub-extraction）

**改动**：创建 `LLMChannelEditor/` 子目录；types.ts + utils.ts + ChannelRow.tsx + LLMChannelEditor.tsx + index.ts 全部到位；测试文件迁入 `LLMChannelEditor/__tests__/`；调整 SettingsPage.tsx 的 import 路径（settings/index.ts 不变）

**改动量**：~1800 行净搬迁，**不动任何函数体、不动 JSX、不动 className、不动 export 名**

**验证**：
```bash
npm run lint
npm run build
npm test -- --run src/components/settings/LLMChannelEditor/__tests__/LLMChannelEditor.test.tsx
```
所有 37 个测试必须通过，lint + build 必须干净。

**警告消耗**：0（架构搬迁本身不消任何 react-doctor 警告，但为后续每一步铺平道路）

### D2 — ChannelRow 内部子拆

**改动**：从 ChannelRow.tsx 抽出 3 个 sub-panel 文件 —— `ChannelTestPanel.tsx` / `ChannelDiscoveryPanel.tsx` / `ChannelCapabilityPanel.tsx`；ChannelRow 函数体从 403 行降到 ~200 行

**改动量**：3 个新文件 + ChannelRow.tsx 内 JSX 替换为 3 处 `<ChannelXxxPanel ...>` 调用 + props 透传

**验证**：同 D1，重点验证测试覆盖 —— 任何子拆破坏会让 37 个测试中至少 1 个失败

**警告消耗**：1（ChannelRow 的 line 138 `no-giant-component` 归零）

### D3 — A11y 4 改

**改动**：4 处 label-has-associated-control 修复
- L277 (协议 in ChannelRow.tsx): `htmlFor` + `useId()`
- L386 (可选模型 in ChannelDiscoveryPanel.tsx): `<fieldset><legend>` 包整组
- L1659 (Temperature in LLMChannelEditor.tsx): `htmlFor` + `id`
- L1712 (备选模型 in LLMChannelEditor.tsx): `<fieldset><legend>` 包整组

**改动量**：~20 行修改 + 用 Tailwind `border-0 m-0 p-0` 抹掉 `<fieldset>` 默认样式

**验证**：同 D1 + 视觉对比（DOM 文本相同；样式应无可见变化）

**警告消耗**：4

### D4 — Perf 4 改

**改动**：
- L597 `splitModels`: `.map().filter()` → `.flatMap()`
- L962 `parseChannelsFromItems`: 直接调用 `splitModels(...)` 消除重复
- L1016 `activeNames.includes()` in loop: 改用 `Set.has()`
- L1005 `apiKey.includes(',')`: inline disable + reason（String.includes 误报）
- L1413 / L1491 async-defer-await: 现场判定（如确认误报 → inline disable + reason；如确认真实问题 → 重排 await 位置）

**改动量**：~25 行修改 + 3 个 inline `// eslint-disable-next-line ... -- <reason>` 注释

**验证**：同 D1，特别关注 `parseChannelsFromItems` 用 `splitModels` 替代后行为等价

**警告消耗**：6

### 累计

- D1 后：文件警告 14 → 14（架构搬迁不消警告）
- D2 后：14 → 13（消 ChannelRow `no-giant-component`）
- D3 后：13 → 9（消 4 a11y）
- D4 后：9 → 3（消 6 perf）

**最终剩 3 条警告**，全部明确留给 Deep 级专题：
- line 1044 `no-giant-component`（主 editor 760 行函数体）
- line 1050 `prefer-useReducer`（12 useState）
- line 1091 `no-cascading-set-state`（sync useEffect）

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| D1：抽出后 tsc 报路径错误 | 中 | 低 | D1 commit 前必跑 `npm run build`；任何错误就回退路径修改后再 commit |
| D1：37 个测试中有依赖内部实现的（如 mock 内部 helper）会断 | 低 | 中 | D1 commit 前跑测试套件；任一失败先排查 mock 路径，必要时调整测试 import 路径（**不修改测试断言**） |
| D2：ChannelRow 子拆漏传 props 导致 sub-panel 拿不到 state | 中 | 高 | sub-panel 的 props interface 由 TypeScript 强制约束，编译期就抓到漏传；37 个测试集成验证行为 |
| D2：sub-panel 渲染顺序变化导致 React Testing Library 的 queries 找不到元素 | 低 | 中 | sub-panel 内 JSX 与原 ChannelRow JSX 一致（只是物理位置在子组件里）；DOM 结构不变 |
| D3：`<fieldset>` 默认样式破坏视觉 | 中 | 低 | 加 Tailwind `border-0 p-0 m-0` 清零；浏览器手动确认 |
| D4：async-defer-await 现场判定与初判不同 | 中 | 低 | 实施时仔细读，转为真实重排（不需要回退已 commit 的工作） |
| 与活跃 feat 分支合并冲突 | 极低 | 中 | LLMChannelEditor 不在 `feat/trading212-csv-import` 和 `feat/portfolio-realtime-price-polling` 的改动面 |

## 7. 回滚

每个 commit 独立 `git revert <sha>` 即可：
- D1 回滚 = 全部撤回，回到现状
- D2 回滚 = 保留架构搬迁、撤回 ChannelRow 子拆
- D3 回滚 = 保留 D1+D2、撤回 a11y 修复
- D4 回滚 = 保留 D1+D2+D3、撤回 perf 修复

## 8. 验收清单

- [ ] D1 commit：`LLMChannelEditor/` 目录创建完成，5 个新文件就位（LLMChannelEditor.tsx + ChannelRow.tsx + types.ts + utils.ts + index.ts）；旧 `LLMChannelEditor.tsx` 删除；test 文件迁入新位置；SettingsPage import 路径更新
- [ ] D2 commit：ChannelRow 内拆出 3 个 sub-panel 文件（ChannelTestPanel + ChannelDiscoveryPanel + ChannelCapabilityPanel）；ChannelRow 函数体降到 <300 行
- [ ] D3 commit：4 处 label-has-associated-control 警告归零
- [ ] D4 commit：2 处 js-flatmap-filter + 1 处 set-map（+1 误报 disable）+ 2 处 async-defer-await 处理完成
- [ ] 每个 commit 后 `npm run lint` clean
- [ ] 每个 commit 后 `npm run build` 绿
- [ ] 每个 commit 后 37 个 LLMChannelEditor 测试全过
- [ ] 全部完成后 `npx react-doctor` 显示 LLMChannelEditor 文件仅剩 3 条 warning（`no-giant-component` 主 editor + `prefer-useReducer` + `no-cascading-set-state`）
- [ ] `docs/CHANGELOG.md` 的 `[Unreleased]` 段追加 `[chore]` 条目记录本次重构

## 9. 不在本次范围内的后续工作

- **主 editor 子拆** —— 主 LLMChannelEditor 760 行函数体需要拆 `RuntimeConfigCard` / `ChannelListSection` / `AddChannelControls` 等子组件才能让 line 1044 `no-giant-component` 归零，留 Deep
- **Deep 级 useReducer 迁移** —— 主 editor 12 useState 合并为 reducer（line 1050 + 1091 警告）
- **ChannelRow 状态下推** —— `testState`/`discoveryState`/`capabilityState`/`expanded` 从父组件 by-index 改为 ChannelRow 内部状态
- **ChatPage / PortfolioPage 类似重构** —— 另开专题，各自的 spec 文档
