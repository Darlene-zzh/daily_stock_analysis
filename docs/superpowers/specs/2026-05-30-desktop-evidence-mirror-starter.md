# Desktop Evidence-Chain Mirror — Initiative Starter (pre-brainstorm)

**Date**: 2026-05-30
**Status**: ✅ RESOLVED 2026-05-31 — initiative is moot (no mirror work needed). See "Resolution" below.
**Parent reference**: `docs/superpowers/specs/2026-05-21-evidence-grounded-decision-pipeline-design.md`
（参见原 spec "非目标" 段："桌面端组件 mirror（本 spec 完成后另立 initiative 单独考虑）"）

---

## Resolution (2026-05-31)

调查 `apps/dsa-desktop/` 实际架构后，**本 initiative 不需要执行**：

- 桌面端是一个 **Electron 壳**，不是独立的 React/Tauri 报告 UI（`package.json`: electron ^31，无 react / vite / tauri）。
- `main.js` 启动内置后端进程后，主窗口直接 `await mainWindow.loadURL('http://127.0.0.1:${port}/')`（约 line 1566），加载的就是**后端服务的同一份 Web 前端**（`static/`，由 `apps/dsa-web` 构建）。
- `renderer/` 目录只有一个 `loading.html` 启动屏；**没有任何独立的桌面报告渲染层**。

因此 Phase 4-5 的证据链组件（`PriceMapCard` / `EvidenceExpansion` / `EvidenceRef` / `StrategyHeroCard` / `PositionFlowTimeline` / `ActionPlanTable`）**在桌面端已经自动呈现**——桌面端就是同一个 web bundle 跑在 BrowserWindow 里。没有"镜像"工作可做。

下面的开放问题（Q1-Q6）建立在"桌面端有/需要自己的报告渲染"这一**错误前提**上，已作废：

- **Q1（框架/复用边界）**：答案是"两者皆非"——桌面端通过 `loadURL` 加载 web app，天然永远同步，无需 symlink/monorepo/重写。
- **Q2（信息密度）/ Q5（跨平台）/ Q6（测试）**：因为渲染的就是 web app，全部沿用 Web 端方案，无桌面专属决策。
- **Q3（实时报价）**：桌面端后端是本地 spawn 的，web app 的 `🔄 刷新` 调用 `GET /api/v1/stocks/{code}/quote` 直接可用。
- **Q4（离线）**：桌面端依赖本地后端进程运行；后端在则 quote 可用，不存在"web 组件 + 无 quote endpoint"的降级场景。

**唯一可能的桌面专属（未来如有需要再单独提）**：启动屏 `loading.html` 的体验、窗口默认尺寸是否适配证据链组件的宽度。均非本 initiative 范畴，且无明确需求，按"稳定性优先"暂不动。

---

## 目的

此文件**不是**一份成形的设计，是为下一次 brainstorm session 准备的"输入材料"：浓缩当前桌面端实际状态、原 spec 留下的边界条件、以及需要在 brainstorm 中明确回答的开放问题。

下一次开 session 时，把这份 starter 喂给 Claude 并说"按 brainstorming skill 走"，可以避免重新 re-explore 已经清楚的部分。

---

## 当前事实

1. **Web 端已完成**：Phase 4-5 落地了 `PriceMapCard` / `EvidenceExpansion` / `EvidenceRef` / `StrategyHeroCard` / `PositionFlowTimeline` / `ActionPlanTable` / `RefreshPriceButton` / `useFactBundle` hook（详见 `apps/dsa-web/src/components/report/`）。
2. **桌面端消费同一份 dashboard JSON**（参见 [[repo-async-task-queue]]）—— `apps/dsa-desktop/` 走 IPC 拿后端响应，schema 与 Web 端一致。
3. **新字段全部 optional** —— `fact_bundle` / `evidence_refs` / `candidate_id` / `provenance` / `tier` / `narrative` 在桌面端当前忽略即可，老桌面端版本不会崩，只是看不到证据链。
4. **后端零变更需要** —— 桌面端 mirror 是纯前端工作。

---

## 关键开放问题（brainstorm 时回答）

### Q1 · 框架与组件复用边界

桌面端用什么 UI 栈？（Electron + React？Tauri + React？原生？）
- 如果同栈 React：能不能把 `apps/dsa-web/src/components/report/` 直接 symlink / monorepo 共享？
- 如果不同栈：是 1:1 重写还是只保留信息结构、视觉重新设计？

### Q2 · 桌面端使用语境差异

桌面端的典型使用场景是不是跟 Web 端不同？比如：
- Web 端：浏览器里看完整报告，可能有外部浏览器去 click-through
- 桌面端：可能在交易窗口边上常驻 + 多股切换更频繁，**信息密度 vs 留白**的偏好可能不一样

如果场景真的不同，PriceMapCard 这种"价位地图"在桌面端也许该改成更紧凑的"价位条"。

### Q3 · 实时报价刷新机制

Web 端走 `GET /api/v1/stocks/{code}/quote` + 用户点击 "🔄 刷新" 按钮。桌面端要不要：
- 同样的手动刷新模式（保守，token 成本可控）
- 自动 N 秒轮询（更"专业终端"感，但耗 API 配额）
- 系统级 push（如果未来后端有 WebSocket，桌面端最适合接入）

### Q4 · 离线模式

桌面端是否需要支持离线浏览历史报告？如果是，证据链组件必须能在无 quote endpoint 的情况下 graceful 降级（不显示"距现价"动态数字、不出现刷新按钮）。

### Q5 · 跨平台差异

macOS / Windows / Linux 在原生组件上有差异（菜单栏、键盘快捷键、字体抗锯齿）。证据折叠面板（`EvidenceExpansion`）在不同平台的展开动画是否要原生化？

### Q6 · 测试策略

桌面端的端到端测试现在怎么跑？Playwright? Electron 测试框架？决定了证据链组件能不能复用 Web 端的 `*.test.tsx`。

---

## 已经定的边界（无需再讨论）

- ❌ 不重新设计证据卡片的**信息层级**——4 类（技术 / 委员会 / 情报 / 量化）已经在 [Web Phase 5 spec C 段](../specs/2026-05-21-evidence-grounded-decision-pipeline-design.md#section-c--渲染层) 锁定。
- ❌ 不引入新的 fact 类型 —— 8 类已经穷尽（technical / quant / committee / intel / portfolio / flow / chip / candidate）。
- ❌ 不让桌面端走独立的后端 API —— `dashboard.fact_bundle` 是单一真源，桌面端只是另一个 consumer。
- ✅ 4 个核心 section（PriceMap / AI 推荐策略 / 持仓操作计划 / 仓位流水）的内容契约不变。

---

## 建议的 brainstorm 起点

下次开 session 时建议：

1. 先让 Claude 读这份 starter
2. Claude 用 brainstorming skill 启动，**直接跳过 "Explore project context"**（已在这份 starter 里）
3. 从 Q1（框架与组件复用边界）开始问，因为 Q1 的答案约束所有后续问题
4. 根据 Q1 的答案，可能能省下 Q5、Q6 的讨论（如果桌面端就是 Electron + React 同栈，平台差异和测试策略大概率沿用 Web 端方案）

---

## 不要做的事

- ❌ **不要从这份 starter 直接跳到写代码** —— starter 不是 spec，开放问题没回答前 mirror 工作没法启动。
- ❌ **不要预先假设答案** —— Q1 可能是 Electron + React，也可能用户想换 Tauri；让 brainstorm 自然走出来。
- ❌ **不要把 Web 端组件无脑 1:1 镜像** —— 上面 Q2 提示桌面端使用场景可能不同，pixel-perfect 复制不一定是正解。

---

## 历史决策溯源

如需了解 Web 端为什么这么设计（B 风格内嵌可展开 / C 风格价位地图 / 4 section 合并自原 5 字段），读 `2026-05-21-evidence-grounded-decision-pipeline-design.md` 的 "用户在此问题确认的方向选择" 段。

桌面端 mirror 不必继承所有 Web 端的视觉决策——这份 starter 的目的之一就是问"哪些应该继承，哪些不该"。
