# Adaptive Strategy Classification + Multi-Source Sentiment — Design

**Date**: 2026-05-16
**Status**: Approved (pending written-spec review)
**Scope**: 让 LLM 对**所有**单股分析（A 股 / 港股 / 美股，带持仓或不带持仓）先按四种交易策略
做分类（每只股可适用多种，但只推荐一种），针对推荐策略生成符合该策略 logic 的操作计划，
显著提升 action_plan_items 的可执行性。同时把市场情绪（Reddit / X / Polymarket / News）
作为策略分类的显式输入并在报告里专门展示。

**适用范围**：

| 场景 | strategy_choices 生成 | action_plan_items | sentiment_dimensions |
|---|---|---|---|
| 美股 + 带持仓 | ✅ 全部 4 个策略可选 | ✅ 按 cost-aware 模板 | ✅ 全 5 源（Reddit/X/Poly/News/StockTwits）|
| 美股 + 未持仓 | ✅ 但 `stepped_profit_taking` 自动 applicable=false（无浮盈可锁） | ✅ 按未持仓建仓模板 | ✅ 同上 |
| 港股 / A 股 + 带持仓 | ✅ 全部 4 个策略可选 | ✅ 按 cost-aware 模板 | ⚠️ null（Adanos / StockTwits 仅覆盖美股） |
| 港股 / A 股 + 未持仓 | ✅ stepped_profit_taking 不适用 | ✅ 按未持仓建仓模板 | ⚠️ null |
| **任何场景** | 始终生成 strategy_thesis（基于可用数据） | 始终非空（最少 1 条） | 缺失维度 UI 自动隐藏 |

不带持仓场景下：
- `long_term_hold` / `swing_trade` / `wait_and_see` 仍然可选（cost-based 规则降级为基于现价的相对规则，例如 stop_loss 用现价 × 0.9 而非 cost × 0.9）
- `action_plan_items` 的「股数」字段表达为建仓数（按权益 % 推算，未带 portfolio 则纯定性描述 "小仓试探"）

---

## 背景

现有 `action_plan_items` 区块（2026-05-16 早间已上线）存在四个核心问题：

1. **方向标签与用户处境不匹配** — chart 上的 stop_loss / take_profit 直接被 LLM 当成方向 enum，没考虑用户成本基础
2. **建议机械、无叙事** — 每个 item 是孤立 if-then trigger，没有「这只股值得用什么策略对待」的串联
3. **触发价太紧** — 经常出现距现价 < 1% 的触发，几乎等于「立刻执行」
4. **item 之间无依赖** — 多条 items 同时存在，但执行顺序、互斥关系、shares 闭合无说明

同时市场情绪虽然已经接入（Adanos API），但：

- Reddit endpoint 一直 404（path 写错，本 spec 实现前已修复）
- 数据进了 LLM 但没有 dashboard 上专门的展示区
- 没有作为策略分类的显式输入

本 spec 解决上述全部问题。

---

## 数据契约

### 1. `dashboard.core_conclusion` 新增字段

```jsonc
"core_conclusion": {
  // ... 现有字段 (one_sentence, time_sensitivity, signal_type, position_advice)

  "strategy_choices": [
    {
      "id": "long_term_hold",         // enum 固定 4 个值
      "label_zh": "长线持有",
      "emoji": "🌳",
      "applicable": true,             // false 时 LLM 须在 reason 里说明为何不适用
      "fit_condition": "看好 AI 主线 1-2 年逻辑",
      "key_params": "不设硬性止盈；跌破 $176（cost -10%）才退出",
      "time_horizon": "6 个月+",
      "inapplicable_reason": null     // applicable=false 时必填，否则 null
    },
    // ... 0-3 more entries
  ],
  "recommended_strategy": "stepped_profit_taking",  // 必填，与上面某条 id 对应
  "strategy_thesis": "NVDA 当前 MA5>MA10>MA20 多头排列... 建议按阶梯止盈对待... 优势是锁定胜利成果同时不放弃趋势继续；缺点是若突破后再大涨会少赚一些。",

  "action_plan_items": [/* 现有 11 字段结构，绑定 recommended_strategy 模板 */],

  "position_outcome_summary": {
    "remaining_shares_after_all_triggers": 0.0,
    "worst_case_loss_pct": -10.0,
    "worst_case_loss_amount": -12.0,
    "worst_case_currency": "GBP",
    "best_case_gain_pct": 30.0,
    "best_case_gain_amount": 36.0,
    "risk_reward_ratio": "1:3"
  }
}
```

### 2. `dashboard.intelligence.sentiment_dimensions` 新增字段

替代/扩展现有的散文式 `sentiment_summary` 字段：

```jsonc
"intelligence": {
  // ... 现有字段
  "sentiment_dimensions": {
    "reddit": {
      "buzz_score": 84.4,
      "buzz_trend": "rising",          // rising / falling / stable / null
      "sentiment_score": 0.056,         // -1.0 to +1.0
      "mentions_7d": 3184,
      "bullish_pct": 30,
      "bearish_pct": 17,
      "subreddit_count": 50,
      "top_subreddits": ["wallstreetbets", "stocks", "ValueInvesting"],
      "source": "adanos"
    },
    "x_twitter": {
      "buzz_score": 89.0,
      "buzz_trend": "falling",
      "sentiment_score": 0.278,
      "mentions_7d": 1099,
      "source": "adanos"
    },
    "polymarket": {
      "buzz_score": 64.7,
      "sentiment_score": 0.125,
      "trade_count": 70,
      "source": "adanos"
    },
    "news": {
      "buzz_score": 61.6,
      "buzz_trend": "stable",
      "sentiment_score": 0.484,
      "mentions_7d": 285,
      "bullish_pct": 86,
      "bearish_pct": 4,
      "top_sources": ["yahoo-finance", "motley-fool", "tipranks"],
      "source": "adanos"
    },
    "stocktwits": {
      "bullish_ratio": 0.62,            // 0.0 to 1.0
      "bearish_ratio": 0.18,
      "neutral_ratio": 0.20,
      "messages_sampled": 50,
      "source": "stocktwits_public"
    },
    "divergence_signal": "retail_bullish_institutional_neutral",  // optional, LLM-emitted
    "summary_zh": "散户论坛热度上升但 X 热度回落；新闻情绪明显积极但 Polymarket 等中等..."
  }
}
```

所有字段 optional —— 数据源不可用时省略对应 key，UI 自动隐藏。

---

## 设计

### 1. 策略池（4 个固定 strategy ID）

| id | zh | emoji | 使用场景 | items 长度 | 必含元素 | 禁止元素 |
|---|---|---|---|---|---|---|
| `long_term_hold` | 长线持有 | 🌳 | 看好长期逻辑，能容忍短线波动 | 2-3 | 1 个 cost × 0.85~0.9 真 stop_loss；1 个 add-on at cost × 0.85 | 短线 trigger（距现价 < 5%） |
| `swing_trade` | 短线波段 | ⚡ | 跟随 chart 信号短期博弈 | 3-4 | 1 entry/sell + 1 chart stop（MA20 / 支撑下）+ 1 take_profit | cost-based stop（短线不看 cost） |
| `stepped_profit_taking` | 阶梯式止盈 | 🪜 | 已有浮盈，希望分批锁定 | 3-4 | 2-3 个阶梯 take_profit + 1 个 cost-based protection stop | buy item（已盈利不再加仓） |
| `wait_and_see` | 暂不操作 | 🚪 | 事件临近（财报/政策），先观察 | 0-1 | 至多 1 个 "事件触发后重判" 提醒 | 任何价格 trigger |

`recommended_strategy` 字段值必为以上 4 个 id 之一。
`strategy_choices` 是 LLM 实际填的可选列表，长度 1-4，跳过明显不适用的（applicable=false 也可以列出但要给 inapplicable_reason）。

### 2. 策略分类的 LLM 决策规则

写在 `_try_inject_action_plan_items` 的新 prompt（实际工作是「strategy_classify_and_plan」）：

```
你需要先判断当前股票适合哪些策略，再针对推荐策略生成对应的 action_plan_items。

## 第一步：策略分类

阅读以下输入：
- 用户持仓上下文（成本价、浮盈浮亏、持有天数）
- 技术摘要（趋势、MA 排列、支撑/压力位）
- 基本面与新闻摘要
- 市场情绪（Reddit / X / Polymarket / News）

按以下规则在 4 个固定策略里挑选 applicable 状态：

| 触发条件 | 推荐 / 适用 |
|---|---|
| 持仓盈利 > +5% + 技术结构未坏 + buzz falling 或 sentiment 降温 | 推荐 `stepped_profit_taking` |
| 持仓盈利 > +5% + 技术结构强 + buzz rising + bullish sentiment | 推荐 `swing_trade` 或 `long_term_hold`（按时间维度偏好） |
| 持仓亏损 -3% ~ -15% + 基本面叙事完好 | 推荐 `long_term_hold`（分批补仓在 thesis 里）或 wait_and_see |
| 持仓亏损 > -15% + 基本面恶化 / sentiment 转负 | 推荐 `wait_and_see`（评估认错或继续等） |
| 未持有 + 趋势强 | 推荐 `swing_trade` |
| 未持有 + 趋势弱 + 估值偏高 | 推荐 `wait_and_see` |
| 财报 / 政策事件 < 14 天 + 持仓 | 推荐 `wait_and_see` |

`applicable=false` 的策略也要列出并填 inapplicable_reason（让用户看到完整对比）。
推荐 1 个策略放在 `recommended_strategy`。

## 第二步：thesis 论述

用 100-200 字解释为什么推荐该策略，必须显式引用：
- 用户持仓状态（成本、浮盈/亏、持有天数）
- 至少 1 条技术依据（具体指标数值）
- 至少 1 条情绪依据（buzz 数值或 trend）
- 该策略的优势 + 劣势

## 第三步：生成 action_plan_items

严格遵循推荐策略的模板：

- recommended_strategy = `long_term_hold` →
  必含 1 条 `direction=stop_loss` 且 trigger_price ≤ avg_cost × 0.9；可选 1 条 `direction=buy`
  在 cost × 0.85 附近作为 add-on；禁止短线 trigger（距现价 < 5%）。共 2-3 条。
- recommended_strategy = `swing_trade` →
  必含 1 条 entry (buy/sell)、1 条 `direction=stop_loss`（chart-based，可在 cost 上方）、
  1 条 `direction=take_profit`（chart-based）；可选第 4 条次级 entry。共 3-4 条。
- recommended_strategy = `stepped_profit_taking` →
  必含 2-3 条 `direction=take_profit`（不同阶梯价位）+ 1 条 `direction=stop_loss`（cost × 0.95
  作 protection）；禁止 `direction=buy`。共 3-4 条。
- recommended_strategy = `wait_and_see` →
  至多 1 条 item，且必须是事件类提醒（无价格 trigger），如「财报后重新评估」。共 0-1 条。

任何违反上述模板的 item 在 post-process 阶段会被丢弃或重写。
```

完整 prompt 文本在实现时落到 [`src/services/portfolio_context_service.py`](../../src/services/portfolio_context_service.py) 的 `ACTION_PLAN_INSTRUCTION_ZH` 常量里，或独立成 `STRATEGY_CLASSIFY_INSTRUCTION_ZH`。

### 3. 报告质量五条规则（post-process 强制）

实现在 `_try_inject_action_plan_items` 解析后的 sanitization 步骤里：

1. **真 stop_loss 强制存在** —
   - `recommended_strategy ∈ {long_term_hold, stepped_profit_taking}` 时，items 中必须存在至少一条
     `direction=stop_loss` 且 `trigger_price ≤ avg_cost × 0.95`
   - 不存在时由 post-process 自动追加（基于 avg_cost × 0.9）
2. **触发距离守门** —
   - 任何 `trigger_price` 距 `current_price` < 2.5% 时，要么 LLM 重写，要么 post-process 标注 `"⚠️ 触发紧贴现价"` 在 trigger_condition 里
3. **股数闭合** —
   - 推荐策略下所有 items 的 `shares` 总和必须 ≈ 用户持仓数（容差 ±5%）
   - 不闭合时 post-process 追加一条 `priority=99` 的 "剩余 N 股不动作" 注释项
4. **item 假设独立性** —
   - 每条 item 在 prompt 中假设 "其他 item 未执行"，前端 UI 在每条 item 末尾追加一行说明文字
5. **空 quant 字段** —
   - quant_signal 无数据时填 `null`（不要填空字符串 `""`），renderer 已能跳过 null

### 4. 情绪数据获取（A + B + C 全集）

**A. 修复 Adanos Reddit endpoint** ✅ 已完成
- `src/services/social_sentiment_service.py:154` path 从 `/reddit/stocks/v1/report/{ticker}`
  改为 `/reddit/stocks/v1/stock/{ticker}`

**B. 新增 StockTwits 公开 API（免费、无 key）**

新建 `src/services/stocktwits_service.py`，单个 endpoint：

```
GET https://api.stocktwits.com/api/2/streams/symbol/{TICKER}.json
```

返回最近一批 (≤30) 散户 message，每条 `entities.sentiment.basic` ∈ {"Bullish", "Bearish", null}。
聚合：

```python
{
  "bullish_ratio": bullish_count / total,
  "bearish_ratio": bearish_count / total,
  "neutral_ratio": neutral_count / total,
  "messages_sampled": total,
  "source": "stocktwits_public"
}
```

特性：
- 无 API key（公共 endpoint）
- 限流：~200 req/h 每 IP，加 60s TTL 缓存避免重复调用
- US tickers only（与 Adanos 同范围）
- 网络失败时 silent fail，不影响主流程

**C. 新增 Adanos News Sentiment endpoint（同 key 已有）**

修改 `src/services/social_sentiment_service.py`，新增 `fetch_news_report(ticker)`：

```
GET https://api.adanos.org/news/stocks/v1/stock/{TICKER}
```

返回 buzz_score / sentiment_score / mentions / bullish_pct / bearish_pct / top_sources。
直接复用现有 `_fetch_json` 基础设施，不需要新 API key 或新依赖。

**整合**：`get_social_context(ticker)` 扩展为返回结构化 dict（而非现在的纯文本 block），
并在 `pipeline.py` 注入时同时填到：
- `news_context`（继续给 LLM 看，文本形式）
- `dashboard.intelligence.sentiment_dimensions`（结构化形式给 dashboard）

### 5. 报告版式

#### 新增 section: 📌 策略选择（在 核心结论 之后、数据透视 之前）

```
═══════════════════════════════════════════════════════
📌 策略选择
═══════════════════════════════════════════════════════

可选策略对比

| 策略 | 适用条件 | 关键参数 | 时间维度 |
|---|---|---|---|
| 🌳 长线持有 | 看好 AI 主线 1-2 年逻辑 | 跌破 $176（cost -10%）才退出 | 6 个月+ |
| ⚡ 短线波段 | ⚪ 不适用（你已 +15% 浮盈，应该兑现而非进出） |  |  |
| 🪜 阶梯式止盈 | 已 +15% 浮盈，希望分批锁定 | $236/$245/$255 三段减仓 | 滚动 |
| 🚪 暂不操作 | 5/20 财报临近，先观察 | 当前 hold；5/20 后重新判断 | 视事件而定 |

🎯 AI 推荐策略：🪜 阶梯式止盈

NVDA 当前 MA5>MA10>MA20 多头排列、MACD 多头、RSI 在强势区，
AI 算力主线未破坏。但你已 +15% 浮盈，5/20 财报临近、估值偏高、
X buzz 89 falling 显示社交热度回落——继续等更高目标位的边际
收益递减。建议按阶梯止盈对待：分批兑现已实现盈利、保留 1/3
仓位等中期突破。优势是锁定胜利成果同时不放弃趋势继续；
缺点是若突破后再大涨会少赚一些。
```

#### 「持仓操作计划」改为推荐策略的展开（在策略选择之后）

```
📋 操作计划（按推荐策略 🪜 阶梯式止盈 展开）
① 🎯 第一段止盈 @ $236.54 (priority 1)
② 🎯 第二段止盈 @ $250.00 (priority 2)
③ 🛑 真·止损 @ $176 (priority 3)

─────────────────────────────────────────
执行 ①②③ 后：剩余 0 股 / 0 GBP 暴露
最差止损：-£12（cost -10%）
最好止盈：+£36（+30%）
风险回报比 (R:R)：1 : 3
─────────────────────────────────────────
```

#### 「📱 市场情绪」subsection（数据透视 之内或之后）

```
📱 市场情绪 (Sentiment)

机构 / 媒体              散户 / Social
━━━━━━━━━━━━━━━━━━━━    ━━━━━━━━━━━━━━━━━━━
📰 News    +0.48 ↗ stable    🔴 Reddit  +0.06 ↗ rising (84/100)
                              🐦 X       +0.28 ↘ falling (89/100)
                              💬 StockTwits  Bull 62% / Bear 18%
                              🔮 Polymarket  +0.13 (mild)

⚖️ 分歧信号：散户 / X 出现降温，但 Reddit 与机构媒体仍偏积极
```

### 6. 前端

- 新组件 [`apps/dsa-web/src/components/report/StrategySelector.tsx`](../../apps/dsa-web/src/components/report/StrategySelector.tsx)
  - 横向 4 列卡片（移动端纵向），每张卡含 emoji + label + fit_condition + key_params + time_horizon
  - applicable=false 的卡片灰显，hover 显示 inapplicable_reason
  - recommended_strategy 对应的卡片高亮 + 推荐徽章
- 新组件 [`apps/dsa-web/src/components/report/StrategyThesis.tsx`](../../apps/dsa-web/src/components/report/StrategyThesis.tsx) — 一段 prose
- 新组件 [`apps/dsa-web/src/components/report/SentimentPanel.tsx`](../../apps/dsa-web/src/components/report/SentimentPanel.tsx) — 两列布局展示 5 个情绪源
- 新组件 [`apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx`](../../apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx) — 表格 / 卡片展示 R:R
- 现有 `ActionPlanTable` 不变；只是它的容器 section 标题改为「📋 操作计划（按推荐策略 X 展开）」

`ReportSummary.tsx` 接入顺序：

```
ReportOverview              （现有，核心结论 in here）
StrategySelector            ← 新
StrategyThesis              ← 新
ActionPlanTable             （现有；标题动态注入推荐策略名）
PositionOutcomeSummary      ← 新
ReportStrategy              （现有作战计划）
SentimentPanel              ← 新（在 ReportDetails 之前）
ReportNews
ReportDetails
```

---

## 影响范围

| 文件 | 改动类型 |
|---|---|
| `src/services/portfolio_context_service.py` | 扩展 prompt，加 strategy_classify_and_plan 指令；扩展 synthesize_action_plan_items 支持 strategy_id 模板 |
| `src/analyzer.py` `_try_inject_action_plan_items` | 拼接新 prompt；解析返回的 strategy_choices/recommended/thesis；post-process 五条强制规则 |
| `src/services/social_sentiment_service.py` | 加 `fetch_news_report`；`get_social_context` 返回 structured dict（兼容旧文本 API） |
| `src/services/stocktwits_service.py` | 新文件，~80 行 |
| `src/core/pipeline.py` | 注入扩展的 sentiment_dimensions 到 `dashboard.intelligence` |
| `src/agent/executor.py` AGENT_SYSTEM_PROMPT / LEGACY | JSON 例子加 strategy_choices / recommended_strategy / strategy_thesis / sentiment_dimensions |
| `api/v1/schemas/history.py` | `CoreConclusionSchema` 加 strategy_choices / recommended_strategy / strategy_thesis / position_outcome_summary；`IntelligenceSchema`（如果有）/dict 加 sentiment_dimensions 类型 |
| `src/notification.py` + `src/services/history_service.py` | 双 renderer 镜像新 section 渲染；处理 applicable=false 灰显；情绪 panel；R:R 表 |
| `src/report_language.py` | 加 zh/en label：strategy_section_heading / sentiment_section_heading / 4 个策略 label / position_outcome_label |
| `apps/dsa-web/src/types/analysis.ts` | 加 StrategyChoice / SentimentDimensions / PositionOutcomeSummary 类型 |
| `apps/dsa-web/src/components/report/StrategySelector.tsx` | 新文件 |
| `apps/dsa-web/src/components/report/StrategyThesis.tsx` | 新文件 |
| `apps/dsa-web/src/components/report/SentimentPanel.tsx` | 新文件 |
| `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx` | 新文件 |
| `apps/dsa-web/src/components/report/ReportSummary.tsx` | 接入新 4 个组件 |

不改动：`data_provider/`、桌面端、调度器、`src/agent/orchestrator.py`（多 agent 编排不直接产
strategy_choices，依然由 `_try_inject_action_plan_items` 后处理生成）。

---

## 向后兼容

- 所有新字段 optional —— 旧分析记录无 `strategy_choices` 等字段 → renderer 回退到旧的 ActionPlanTable
- 未带 portfolio context 的分析：**仍然触发** strategy classification（按上方「适用范围」表），但 cost-based 规则降级为基于现价的相对规则；`action_plan_items` 的 `pct_of_position` / 持仓相关字段为 null
- 未配置 `SOCIAL_SENTIMENT_API_KEY` 时：`sentiment_dimensions` 为 `null`，UI section 自动隐藏
- StockTwits 失败/超时：单维度缺失，其它正常展示

---

## 非目标

- 不做实时订单执行或券商 API 对接
- 不做策略回测验证准确性
- 不引入新的 LLM 模型选择（gpt-5.5 已经定）
- 不改变现有 `battle_plan` 区块（仍展示 chart-derived 单点价位作交叉参考）
- 不为 A/HK 股做 sentiment_dimensions（Adanos + StockTwits 均仅覆盖美股；A/HK 股 sentiment_dimensions 为 null）

---

## 风险

| 风险 | 缓解 |
|---|---|
| LLM 不遵循 strategy template（emit `buy` item 给 stepped_profit_taking 策略等） | post-process 守门强制校验：strategy → items 类型白名单；违反规则的 item 直接丢弃 |
| 真 stop_loss post-process 追加时，价位 cost × 0.9 可能与 chart 完全脱钩（chart 还在更高位置）| trigger_condition 文字明示「基于成本基础的硬底线，非技术信号」 |
| 股数闭合校验产生「剩 N 股不动」注释项 → 看起来像系统 bug | UI 给这种 priority=99 注释项 distinct 样式（灰色、`📌 持有剩余` 而非编号） |
| StockTwits 频率限制 200/h，重度用户可能触发 429 | TTL 缓存 60s + per-ticker 缓存 5min；缓存命中率应 > 90% |
| Adanos 配额 250/月，多源调用可能加速耗尽 | 4 个 Adanos endpoint 共享 quota；建议每次分析 ≤ 4 次调用（reddit/news/x trending/polymarket trending） |
| sentiment_dimensions 在 prompt 里堆叠过多 token | 给 LLM 的浓缩版本只含 buzz/sentiment/trend，省略 top_subreddits / top_sources |
| 多策略对比表在移动端表格滚动体验差 | 移动端纵向布局，每个策略一张卡 |

---

## 测试重点

- `test_strategy_classification.py`（新）：
  - 持仓 +15% 盈利 + buzz falling → 推荐 `stepped_profit_taking`
  - 持仓 -8% 亏损 + 基本面完好 → 推荐 `long_term_hold`
  - 财报 7 天内 + 持仓 → 推荐 `wait_and_see`
- `test_action_plan_strategy_template.py`（新）：
  - 各策略 items 长度 / 类型符合白名单
  - `long_term_hold` 必含 cost × 0.9 的真 stop_loss
  - `stepped_profit_taking` 不允许出现 `buy` direction
  - `wait_and_see` 最多 1 个 item
- `test_sentiment_dimensions.py`（新）：
  - Adanos news endpoint mock 返回结构正确解析
  - StockTwits public API mock parsing
  - 单维度失败（reddit 404）时其它维度仍正常聚合
- `test_position_outcome_summary.py`（新）：
  - shares 闭合 ±5% 容差
  - R:R 计算正确
- 现有 `test_action_plan_*.py`（更新）：
  - 旧字段保持向后兼容，无 `strategy_choices` 时回退到现有 ActionPlanTable 渲染
