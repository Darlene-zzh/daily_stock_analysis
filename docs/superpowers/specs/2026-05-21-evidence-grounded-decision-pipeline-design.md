# 证据接地的决策管线 — Design

**Date**: 2026-05-21
**Status**: Approved (pending written-spec review)
**Scope**: 把首页个股分析报告里 5 个核心决策字段从「LLM 模板感」改造成「代码接地 + LLM 选择 + 完整证据链」的三阶段管线，覆盖后端 schema、prompt、sanitizer、双 renderer、前端组件库重做。

---

## 背景

用户在使用首页「完整分析」报告时反馈：**持仓操作计划、策略点位、策略选择、AI 推荐策略、仓位流水汇总 这 5 个核心决策字段"看起来像套模板"，缺乏跟实际行情、委员会观点、量化信号、新闻情报的真实绑定**。

### NVDA 报告诊断（id=13, 2026-05-21 00:43 UTC）

抽样诊断证实问题真实存在：

**真实数据齐全**：
- `data_perspective` 含完整技术位：现价 223.47 / MA5=225.49 / MA10=222.02 / MA20=213.40 / 阻力=226.13 / RSI(12)=71.1
- `committee` 跑通 4 位 master + PM 裁决（5.8/10 hold）+ 风控建议仓位 ≤30%
- `intelligence.risk_alerts` 引用了 RSI 71.1 与估值缺失
- `battle_plan.sniper_points` 用了真实技术位（ideal_buy=222.02 / stop_loss=213.39 / take_profit=226.13）
- qlib predictions 可用：NVDA score=0.235, rank=0.847（US 池前 15%），IC_4w=0.21

**`action_plan_items` 完全没用上**：
| # | trigger | 算法 | 问题 |
|---|---|---|---|
| 1 | $205.99 | cost × 1.05 | 已低于现价 $223.47，永不触发 |
| 2 | $219.72 | cost × 1.12 | 已低于现价，已过期 |
| 3 | $235.41 | cost × 1.20 | 与阻力位 $226.13、MA 都对不上 |
| 4 | $176.56 | cost × 0.90 | MA20=$213.40 才是真实技术止损 |

所有 4 条 `quant_signal: null`、`technical_basis: "首档止盈：覆盖手续费与短期波动"`（万能模板）、`fundamental_basis: "落袋为安第一档"`（无意义） — 典型 Tier-2 cost-based 合成产物。

### 根因（综合）

1. **价位决策权完全交给 LLM** — LLM 写 `trigger_price: 421` 是凭想象，无市场结构约束
2. **Tier-2 合成兜底基于 cost × X** — 当 LLM 失败，代码用零售启发式硬编码补，进一步加剧"模板感"
3. **Sanitization 强加 cost-based stop_loss** — `_STRATEGY_HELD_COST_BASIS_ADDENDUM` 等规则把 LLM 给的细节剥掉
4. **量化信号 `quant_signal: null` 全员** — qlib 模型已就绪但未真正接到决策层
5. **委员会输出未塑造 action plan** — PM 5.8/10 hold、风控建议仓位 30%、Cathie 异议这些关键信号没流进操作计划
6. **`battle_plan.sniper_points` 与 `action_plan_items` 矛盾** — 同份报告里两套不一致的止损/止盈位

### 用户在此问题确认的方向选择

- 完整证据审计层（option C）— 每个决策可溯源到原始 fact
- B 风格内嵌可展开 UI（点击展开技术/委员会/情报/量化 4 类证据）
- C 风格价位地图（水平价格轴 + 关键位 + 距离 % + 手动刷新）
- 合并「策略选择」与「AI 推荐策略」 — 4 个核心 section 而非 5 个
- 实时价格走「混合模式」 — 默认快照 + 手动刷新按钮
- 量化范围走「完整」 — A 股全维度，US/HK 退化到 qlib + 基础技术
- 全管线重构（option C）— 接受 ~2700 行净改动 / 6 phase 拆分

---

## 范围

### 改动入口

- 分析管线：`src/analyzer.py` → `src/pipeline.py` → `src/orchestrator.py`
- 持仓上下文：`src/services/portfolio_context_service.py`（synthesize 函数重写）
- 双 renderer：`src/notification.py` + `src/services/history_service.py::_generate_single_stock_markdown`
- API：`api/v1/endpoints/quote.py`（新建）+ router 注册
- 前端：`apps/dsa-web/src/components/report/` 整套重做
- 类型：`apps/dsa-web/src/types/analysis.ts` 扩展

### 不改动

- 多 agent orchestrator 的 `_assemble_dashboard` 逻辑（committee 装配链路）
- Committee 自身（masters / debate / PM / risk officer 流程）
- 大盘复盘（market review）
- 美股个股双语速览（见 `docs/superpowers/specs/2026-05-15-portfolio-aware-and-us-bilingual-report-design.md`）
- 桌面端 `apps/dsa-desktop/`（本 spec 完成后另立 initiative 单独考虑）
- 历史分析记录回填（向后兼容由 renderer fallback 处理）
- 数据源 fallback 链（[[repo-strategy-classification-architecture]] 三层降级保留）

---

## 目标 & 非目标

### 目标

1. **每个 trigger_price 必须基于真实市场结构** — MA / 阻力 / 支撑 / ATR / R-multiple / Fib，禁止 LLM 凭空创造价位
2. **每个决策字段有完整证据链** — UI 上任何数字可 click-through 到 `FactRecord`，含 source 溯源
3. **量化信号真正进决策层** — `quant_signal` 不再为 null
4. **委员会输出塑造操作计划** — PM 评分、风控建议仓位、Master 投票均可作为 evidence 引用
5. **provenance 透明** — LLM 写的 vs 代码兜底的清晰标记
6. **UI 留白充足、视觉专业** — 不拥挤，对标 Bloomberg/Morningstar 阅读密度

### 非目标

- 不做实时订单执行 / 券商 API 对接
- 不做历史回测验证建议准确性
- 不重做 committee 内部架构
- 不引入新的 LLM 提供商或推理框架
- 不强制全实时价格（混合模式：快照 + 手动刷新已够）

---

## 架构

### 三阶段管线

```
┌──────────────────────────────────────────────────────────────┐
│ Stage 1 · Facts Builder（纯代码，确定性）                       │
│ src/analysis/facts_builder.py（新建）                          │
│                                                              │
│ 输入：stock_code, market, portfolio_context, ohlc, committee  │
│ 输出：FactBundle — 结构化 facts 列表 + candidates 候选触发价位 │
│                                                              │
│ Facts 8 分类：                                                │
│   technical.* / quant.* / flow.* / chip.* /                  │
│   committee.* / intel.* / portfolio.* / candidate.*           │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Stage 2 · LLM Decision（消费 FactBundle，输出含 fact_id 决策）  │
│ src/analyzer.py:_try_inject_action_plan_items（重写 prompt）   │
│                                                              │
│ Prompt 给 LLM：                                                │
│   - 完整 FactBundle 作为 context                              │
│   - 候选触发价位菜单（带 ID）                                  │
│   - 要求：从候选里"选"（不"创造"）+ 写理由 + 标 evidence_refs   │
│                                                              │
│ Sanitizer 9 条校验规则；失败回退到代码合成（synthesize_from_   │
│ candidates）。Tier-2 兜底完全基于 candidates 池规则化生成。    │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Stage 3 · Presentation（解析 fact_id，渲染证据链）              │
│                                                              │
│ Backend renderers（双路径 + parity 测试）:                     │
│   notification.py — Wikipedia 风格脚注                        │
│   history_service.py — 镜像格式                               │
│                                                              │
│ Frontend（apps/dsa-web）— B 风格内嵌可展开 +                  │
│ C 风格价位地图：                                               │
│   PriceMapCard / StrategyHeroCard /                          │
│   ActionPlanTable（重写）/ PositionFlowTimeline               │
└──────────────────────────────────────────────────────────────┘
```

### 设计原则

1. **价位决策权从 LLM 收回到代码** — trigger_price 必须来自 `candidates` 池，LLM 只能"选"不能"造"。Sanitizer 拒绝任何 LLM 自创的价位。
2. **每个数据点都有 trace** — UI 上看到的任何数字都能 click-through 到 FactRecord 的 source。
3. **退化路径明确** — Stage 1 总能跑（纯代码）；Stage 2 失败时用 candidates + 规则引擎兜底；Stage 3 永远能渲染。
4. **旧报告兼容** — 历史 `analysis_history` 没 `fact_bundle` → renderer 检测到 schema 版本时回退到当前展示。新字段全部 optional。

### 与现有架构的边界

- **不重做 committee** — committee 是 Stage 1 的输入之一（前置 multi-agent orchestrator 跑完后，其结果 feed 给 facts_builder）
- **不重做 multi-agent orchestrator** — 它的 `_assemble_dashboard` 仍然管 dashboard 装配，但 `_try_inject_action_plan_items` 改为消费 FactBundle
- **不重做 sentiment 5 源** — `intel.sentiment_*` 直接消费 `_latest_sentiment_dims` 现有产物

---

## Section A — FactBundle Schema

### FactRecord 统一形态

```python
# src/analysis/facts.py（新建）

@dataclass
class FactRecord:
    id: str                       # "<type>.<subdomain>.<key>"，如 "technical.ma10"
    type: str                     # 8 个分类之一（见下）
    label: str                    # UI 显示标签，如 "MA10 支撑位"
    value: Any                    # 原始值（float/str/dict）
    display_value: str            # 格式化后展示文本，如 "$222.02"
    unit: Optional[str] = None    # "%", "USD", "shares", "GBP"
    source: str = ""              # 溯源链，如 "data_provider/yfinance:get_realtime_quote@2026-05-21T00:43"
    confidence: Optional[float] = None   # 0-1，软信号才填
    as_of: Optional[str] = None   # ISO 时间戳
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateLevel(FactRecord):
    """price level candidate — Stage 1 预算的可选触发价位"""
    direction: Literal["entry", "exit", "stop", "take_profit"]
    price: float
    basis_fact_id: str            # 这个候选基于哪个 fact，如 "technical.ma20"
    basis_rule: str               # 用了什么规则，如 "ma20_breakdown"
    applicable_strategies: List[str]  # 4 fixed strategy ID 子集
    tier: Literal["primary", "discipline_anchor", "secondary", "filtered"]
    distance_pct_from_current: float


@dataclass
class FactBundle:
    as_of: str                    # ISO timestamp
    market: Literal["a", "hk", "us"]
    stock_code: str
    facts: List[FactRecord]
    candidates: List[CandidateLevel]   # 已过滤掉 tier=filtered 的

    def get(self, fact_id: str) -> Optional[FactRecord]: ...
    def by_type(self, type_prefix: str) -> List[FactRecord]: ...
```

### 8 个 fact type 分类

| Type prefix | 含义 | A 股 | US/HK | 关键字段 |
|---|---|---|---|---|
| `technical.*` | 基础技术指标 | ✅ | ✅ | `current_price` `ma5/10/20` `support` `resistance` `rsi_12` `trend_score` `ma_alignment` `bias_ma10` `volume_ratio` `atr_14` |
| `quant.*` | qlib 量化输出 | ✅ | ✅ | `qlib_score` `qlib_rank` `qlib_ic_current` `qlib_ic_4w` |
| `flow.*` | 资金流（A 股专属） | ✅ | — | `main_net_inflow` `inflow_5d` `inflow_10d` `sector_rank` |
| `chip.*` | 筹码分布（A 股专属） | ✅ | — | `profit_ratio` `avg_cost` `concentration_70` `concentration_90` |
| `committee.*` | 投委会输出 | ✅ | ✅ | `pm_verdict` `pm_score` `pm_dissents` `risk.severity` `risk.suggested_position_pct` `master.<persona>` `debate.<side>.<round>` |
| `intel.*` | 情报/情绪 | ✅ | ✅ | `risk_alert.<i>` `positive_catalyst.<i>` `latest_news` `sentiment_summary` `sentiment.<source>` `earnings_outlook` |
| `portfolio.*` | 持仓上下文 | ✅ | ✅ | `holding_shares` `avg_cost` `unrealized_pnl_pct` `total_equity` `position_match` `first_buy_date` |
| `candidate.*` | 代码预算的候选触发价位 | ✅ | ✅ | `entry.<n>` `exit.<n>` `stop.<n>` `take_profit.<n>` |

### Candidate 生成规则（20 条，专业方法主导）

| 规则 ID | 方向 | 算法 | 适用策略 | tier |
|---|---|---|---|---|
| `resistance_touch` | take_profit | tech.resistance | swing, stepped | primary |
| `resistance_plus_atr` | take_profit | resistance + 1×ATR(14) | stepped, long_term | primary |
| `prev_swing_high` | take_profit | 前 20 日 swing high | swing | primary |
| `r_multiple_2r` | take_profit | current + 2×(current − stop) | swing, stepped | primary |
| `r_multiple_3r` | take_profit | current + 3×(current − stop) | stepped, long_term | primary |
| `fib_extension_1272` | take_profit | 近期波段 127.2% 延伸 | swing | primary |
| `fib_extension_1618` | take_profit | 近期波段 161.8% 延伸 | stepped | primary |
| `psychological_round` | take_profit | 下一个整数关口（$230 / $250） | 所有 | secondary |
| `ma20_breakdown` | stop_loss | tech.ma20 | swing, stepped | primary |
| `support_breakdown` | stop_loss | tech.support | swing | primary |
| `prev_swing_low` | stop_loss | 前 20 日 swing low | swing, stepped | primary |
| `atr_2x_below_current` | stop_loss | current − 2×ATR(14) | swing | primary |
| `atr_3x_below_current` | stop_loss | current − 3×ATR(14) | stepped, long_term | primary |
| `ma10_pullback` | entry | tech.ma10 | swing, stepped | primary |
| `ma20_pullback` | entry | tech.ma20 | swing, stepped, long_term | primary |
| `support_test` | entry | tech.support | swing | primary |
| `breakout_retest` | entry | 前期突破位（变成支撑） | swing, stepped | primary |
| `qlib_top_decile_buy` | entry | 现价（仅 qlib_rank > 0.9 且趋势向上） | long_term | primary |
| `chip_avg_cost` | entry | chip.avg_cost（A 股市场平均成本） | 所有 | primary |
| `cost_plus_5pct` | take_profit | cost × 1.05 | stepped | discipline_anchor |
| `cost_plus_12pct` | take_profit | cost × 1.12 | stepped | discipline_anchor |
| `cost_plus_20pct` | take_profit | cost × 1.20 | stepped, long_term | discipline_anchor |
| `cost_minus_10pct` | stop_loss | cost × 0.9 | long_term | discipline_anchor |

### tier 含义

- **primary**：基于市场结构 / 波动率 / 量化信号 — LLM 优先选这些
- **secondary**：辅助选项（整数关口等）— LLM 可选但不强推
- **discipline_anchor**：基于成本的零售心理锚 — 仅当无 primary 时使用，UI 标 "📌 纪律锚"
- **filtered**：已触发或不可用（cost×1.05 < current_price 等）— 不出现在 prompt 菜单中

### NVDA FactBundle 实例（节选）

NVDA 报告（id=13）跑完 facts_builder 后预期产出形态（实际 bundle 含 ~30 facts + ~13 candidates，此处仅展示代表性 4 条 + 2 个 candidate）：

```jsonc
{
  "as_of": "2026-05-21T00:43:00Z",
  "market": "us",
  "stock_code": "NVDA",
  "facts": [
    {"id": "technical.current_price", "type": "technical",
     "label": "现价", "value": 223.47, "display_value": "$223.47", "unit": "USD",
     "source": "data_provider/yfinance:get_realtime_quote@2026-05-21T00:43"},
    {"id": "technical.ma10", "type": "technical",
     "label": "MA10 (10日均线)", "value": 222.02, "display_value": "$222.02",
     "extra": {"role": "支撑", "bias_pct": 0.65}},
    {"id": "quant.qlib_rank", "type": "quant",
     "label": "Qlib 截面分位", "value": 0.8473, "display_value": "前 15%",
     "confidence": 0.21, "extra": {"universe_size": 503, "rank_absolute": 77}},
    {"id": "committee.risk.suggested_position_pct", "type": "committee",
     "label": "风控建议仓位上限", "value": 0.3, "display_value": "≤ 30%",
     "extra": {"severity": "soft", "red_flags": ["RSI 71.1 超买", "PE/PB 缺失"]}}
  ],
  "candidates": [
    {"id": "candidate.exit.1", "type": "candidate",
     "label": "阻力位触及减仓", "value": 226.13, "display_value": "$226.13",
     "direction": "take_profit", "price": 226.13,
     "basis_fact_id": "technical.resistance", "basis_rule": "resistance_touch",
     "applicable_strategies": ["swing_trade", "stepped_profit_taking"],
     "tier": "primary", "distance_pct_from_current": 1.19},
    {"id": "candidate.stop.1", "type": "candidate",
     "label": "MA20 跌破止损", "value": 213.39, "display_value": "$213.39",
     "direction": "stop_loss", "price": 213.39,
     "basis_fact_id": "technical.ma20", "basis_rule": "ma20_breakdown",
     "applicable_strategies": ["swing_trade", "stepped_profit_taking"],
     "tier": "primary", "distance_pct_from_current": -4.51}
  ]
}
```

---

## Section B — LLM Prompt + Sanitizer + Synthesizer

### Prompt 改造

`_format_prompt` 在已有 portfolio_context_block 之后追加三块新内容：

**第一块 · 事实数据库**（紧凑表格，控制 token）

```
## [事实数据库]
现价 $223.47 (technical.current_price · yfinance · 09:35 UTC)
MA5 / MA10 / MA20 = 225.49 / 222.02 / 213.40 (multi-bias bullish)
RSI(12) = 71.1 (超买区 >70)
阻力 / 支撑 = 226.13 / 222.02
ATR(14) = 4.32

Qlib score 0.235, rank 0.847 (US 池前 15%, IC_4w=0.21)

委员会 PM: hold (5.8/10) · risk soft · 建议仓位 ≤30%
Masters: buffett=hold(4.0), burry=hold(5.0), cathie=strong_buy(9.2 ⚠异议), taleb=hold(5.0)

持仓: 0.7597 股 @ $196.18, 浮盈 +13.33% (+£14.78)
```

**第二块 · 候选触发价位菜单**（LLM 必须从这里选）

```
## [候选触发价位] — 你只能从下表选 trigger_price 的 ID，禁止创造新价位

| ID | 方向 | 价格 | 距现价 | 规则 | 适用策略 | 层级 |
|---|---|---|---|---|---|---|
| candidate.exit.1 | take_profit | $226.13 | +1.2% | 阻力位触及 | swing, stepped | primary |
| candidate.exit.2 | take_profit | $228.50 | +2.2% | 2R 目标 | swing, stepped | primary |
| ... (10-15 条) ...
```

**第三块 · 输出契约**

```
对推荐策略输出 2-4 条 action_plan_items，每条：
- candidate_id: 上表某个 ID（不能是 filtered 的）
- evidence_refs: 至少 2 个 fact_id，引用支持决策的事实
- narrative: 一段论证文本，可内嵌 <ref:fact_id> 标记
- 其他字段（shares/pct_of_position/...）保持现有约束

discipline_anchor 层至多 1 条（仅当无合适 primary）。
```

### Sanitizer 新版（替换 `_sanitize_action_plan_items`）

按顺序执行 9 条校验：

| # | 校验 | 失败处理 |
|---|---|---|
| 1 | `candidate_id` 必须存在于 `FactBundle.candidates` | 整条丢弃 |
| 2 | `trigger_price` 必须 == candidates[candidate_id].price | 强制覆盖为 candidate 价格 |
| 3 | `candidate.applicable_strategies` 必须包含 `recommended_strategy` | 整条丢弃 |
| 4 | candidate 不能是 `filtered` 层 | 整条丢弃 |
| 5 | `direction` 方向逻辑：take_profit > current, stop_loss < current | 整条丢弃 |
| 6 | `evidence_refs` 每个必须有效；少于 2 个时从 `candidate.basis_fact_id` 自动补 | 自动修补 |
| 7 | `discipline_anchor` 层至多 1 条 | 多余的丢弃 |
| 8 | 同一 `candidate_id` 不重复 | 保留 priority 最高的 |
| 9 | sanitize 完成后重排 priority 为 1..N 连号 | — |

校验完后：
- 总条数 = 0 → 标记 LLM 失败，触发兜底
- 总条数 > 0 → 用 LLM 结果

### Synthesizer 重写（替换现有 `synthesize_action_plan_items`）

LLM 失败或被 sanitizer 清零时，代码从 candidates 池规则化生成：

```python
def synthesize_from_candidates(
    candidates: List[CandidateLevel],
    strategy: str,
    facts: FactBundle,
) -> List[ActionPlanItem]:
    """LLM 兜底，基于策略 + candidates 规则化生成。"""
    applicable = [c for c in candidates if strategy in c.applicable_strategies]
    primary_exits = sorted(
        [c for c in applicable if c.direction == "take_profit" and c.tier == "primary"],
        key=lambda c: c.distance_pct_from_current,
    )[:3]
    primary_stops = sorted(
        [c for c in applicable if c.direction == "stop_loss" and c.tier == "primary"],
        key=lambda c: -c.distance_pct_from_current,
    )[:1]
    # 缺 primary 时补 discipline_anchor（最多 1）
    items = []
    for c in primary_exits + primary_stops:
        items.append({
            "candidate_id": c.id,
            "trigger_price": c.price,
            "direction": c.direction,
            "evidence_refs": [c.basis_fact_id, "committee.pm_verdict"],
            "narrative": f"{c.label}：{c.basis_rule}（代码合成）",
            "tier": c.tier,
            "provenance": "synthesized",
            "priority": ...,
        })
    return items
```

每条带 `provenance: "synthesized"` → UI 显示 **🤖 代码兜底** 徽章。

### Dashboard schema 扩展

```typescript
dashboard: {
  ...,
  fact_bundle: FactBundle,  // 新增，顶层

  core_conclusion: {
    ...,
    action_plan_items: [{
      // 现有字段全保留 ...
      candidate_id?: string,
      evidence_refs?: string[],         // 至少 2 个
      narrative?: string,               // 内嵌 <ref:fact_id>
      tier?: "primary" | "discipline_anchor",
      provenance?: "llm" | "synthesized",
    }],
    strategy_thesis: {                   // 从 string 升级为 object
      text: string,
      evidence_refs: string[],
      provenance: "llm" | "synthesized",
    } | string,                          // string 形态兼容旧报告
    strategy_choices: [{
      // 现有字段保留 ...
      supporting_evidence_refs?: string[],
      contradicting_evidence_refs?: string[],
    }]
  }
}
```

所有新字段 optional → 老前端/老 schema 兼容。

### Token 预算

| 项 | tokens |
|---|---|
| 现 prompt | ~5500 |
| FactBundle 紧凑表 | +900 |
| Candidates 菜单 | +600 |
| 输出契约 + 示例 | +400 |
| **新版总 prompt** | **~7400** |

Gemini 2.5 Flash / Pro / Cerebras qwen 都能承受。

---

## Section C — 渲染层

### Backend 双路径

#### 路径 A — `src/notification.py`

通知（Lark / Feishu / Bark）走 Wikipedia 风格脚注：

```markdown
### 📋 持仓操作计划

**① ⬇️ 减仓**（优先级 1）— 触发价 $226.13 [距现价 +1.2%]
- **触发**：阻力位触及¹
- **操作**：卖出 0.2279 股（持仓 30% / 权益 3.5%）
- **依据**：RSI 71.1 超买²，委员会 PM hold（5.8/10）³，风控建议仓位 ≤30%⁴
- **失效**：放量站稳 $230 上方
- 🤖 *代码兜底*（仅当 provenance == synthesized）

---
**证据脚注**
¹ [technical.resistance] 当日阻力位 $226.13
² [technical.rsi_12] RSI(12) = 71.1 进入超买区
³ [committee.pm_verdict] PM 裁决 hold，评分 5.8/10
⁴ [committee.risk.suggested_position_pct] 风控建议仓位上限 30%

查看完整证据链 → http://yourhost/history/{id}
```

新辅助函数 `_render_evidence_footnotes(evidence_refs, fact_bundle)`：
- 收集所有 evidence_refs，编号 ¹²³
- 卡片底部统一渲染脚注列表
- 同 pattern 应用到 `strategy_thesis`、`strategy_choices`

#### 路径 B — `src/services/history_service.py::_generate_single_stock_markdown`

镜像 notification.py 格式。每次改 notification.py 必须同步改这里（[[repo-dual-renderers]] 提醒）。

**关键测试**：`test_renderer_parity` — 两份 renderer 对同一 fixture 输出脚注部分必须字节一致。

### Frontend（apps/dsa-web）

#### 组件清单

| 组件 | 状态 | 职责 |
|---|---|---|
| `PriceMapCard.tsx` | **新建** | C 风格价位地图：水平价格轴 + 关键 levels + 距离 % + 手动刷新按钮 |
| `EvidenceExpansion.tsx` | **新建** | B 风格内嵌可展开证据组（按 type 分组：技术/委员会/情报/量化） |
| `EvidenceRef.tsx` | **新建** | 内嵌引用标签（`<ref:fact_id>` 渲染为可 hover 的小 pill） |
| `ActionPlanTable.tsx` | **重写** | 每条 item 渲染 trigger card + EvidenceExpansion + provenance 徽章 |
| `StrategyHeroCard.tsx` | **新建** | 替换 `StrategyThesis.tsx` + `StrategySelector.tsx` — hero 卡 + alternatives |
| `PositionFlowTimeline.tsx` | **新建** | 替换 `PositionOutcomeSummary.tsx` — 触发时间线 + 汇总卡 |
| `RefreshPriceButton.tsx` | **新建** | 调用 `GET /api/v1/quote/{code}` |
| `useFactBundle.ts` | **新建** | hook — 从 dashboard 提取 fact_bundle，提供 `getFact(id)` lookup |
| `ReportSummary.tsx` | **改造** | 重新编排 4 section（PriceMap → StrategyHero → ActionPlan → PositionFlow） |
| `StrategySelector.tsx` | **删除** | 合并进 StrategyHeroCard |
| `StrategyThesis.tsx` | **删除** | 合并进 StrategyHeroCard |
| `PositionOutcomeSummary.tsx` | **删除** | 替换为 PositionFlowTimeline |

#### EvidenceExpansion 数据契约

```typescript
type EvidenceExpansionProps = {
  evidenceRefs: string[];
  groupBy?: 'type' | 'flat';      // 默认按 type 分组
  defaultOpen?: string[];          // 默认打开的 type
};
```

内部通过 `useFactBundle().getFact(id)` 解析为完整 `FactRecord` 显示。

#### PriceMapCard 数据契约

```typescript
type PriceMapCardProps = {
  currentPrice: number;
  currentPriceAsOf: string;        // ISO timestamp
  levels: Array<{
    factId: string;
    price: number;
    label: string;                  // "MA20" / "止损" / "阻力"
    color: 'red' | 'green' | 'orange' | 'blue' | 'gray';
    role: 'support' | 'resistance' | 'stop' | 'target' | 'ma';
  }>;
  onRefresh?: () => Promise<{price: number; asOf: string}>;
};
```

levels 数据从 `fact_bundle.candidates` + `technical.*` 抽取拼装（前端 helper）。

**关键 UI 约束**：留白充足（用户硬性要求）。每个 level 标签上下错位避免重叠，距离 % 用次级字体灰色显示。

#### Provenance 徽章

```tsx
{item.provenance === 'synthesized' && (
  <span className="badge-synth">🤖 代码兜底</span>
)}
```

### API 新增 endpoint

```python
# api/v1/endpoints/quote.py（新建）
@router.get("/quote/{code}")
async def get_realtime_quote(code: str):
    """轻量端点，返回当前价 + 时间戳。供前端刷新按钮用。"""
    quote = await data_provider.get_realtime_quote_async(code)
    return {
        "code": code,
        "price": quote.price,
        "as_of": quote.as_of.isoformat(),
        "change_pct": quote.change_pct,
    }
```

- 限流：单 IP 60 req/min
- 缓存：1 秒内同 code 复用结果
- 失败：503 而非长时间挂起

### 桌面端

`apps/dsa-desktop/` 当前消费同份 dashboard JSON。新字段全部 optional → 旧桌面端忽略即可。完整证据链体验需要 mirror 组件，**本 spec 完成后另立 initiative 单独安排**，本 spec 不覆盖。

---

## Section D — 测试策略

### 后端测试

| 测试文件 | 覆盖 | 用例数 |
|---|---|---|
| `tests/test_facts_builder.py`（新建） | US/A 股 full bundle、portfolio 缺失、qlib 缺失、ATR 计算、Fib 计算、R-multiple 计算、跨市场降级 | 7-10 |
| `tests/test_candidate_levels.py`（新建） | 每条规则 1 个、tier 分层、已触发过滤、strategy 适配性 | 8-12 |
| `tests/test_sanitizer_v2.py`（新建） | 9 条规则各 1 个正向 + 负向测试 | 18 |
| `tests/test_synthesize_from_candidates.py`（新建） | primary 优先、anchor 兜底、provenance、strategy 过滤、空池、多策略 | 6 |
| `tests/test_evidence_renderer.py`（新建） | footnote 编号、type 分组、缺 fact_bundle 兼容、双 renderer parity | 8 |
| `tests/test_quote_endpoint.py`（新建） | happy path、限流、503、缓存命中 | 4 |
| `tests/test_analyzer.py`（扩展） | prompt 注入测试：FactBundle 序列化、token 增量 | +2-3 |
| `tests/test_pipeline.py`（扩展） | fact_bundle 挂到 dashboard 顶层 | +1-2 |

### 前端测试

| 测试文件 | 覆盖 |
|---|---|
| `useFactBundle.test.ts`（新建） | getFact lookup、缺 id graceful、map 构造 |
| `EvidenceExpansion.test.tsx`（新建） | 渲染 evidence_refs[]、type 分组、空 refs、缺 fact 兜底 |
| `EvidenceRef.test.tsx`（新建） | hover tooltip、点击跳转 |
| `PriceMapCard.test.tsx`（新建） | 多 levels 渲染、refresh 按钮调 API、缺 fact_bundle 回退到 sniper_points |
| `ActionPlanTable.test.tsx`（扩展） | provenance 徽章、evidence_refs 渲染、缺字段兼容 |
| `StrategyHeroCard.test.tsx`（新建） | hero + alternatives 渲染、citation pill 渲染 |
| `PositionFlowTimeline.test.tsx`（新建） | timeline 渲染、汇总卡数字 |
| `RefreshPriceButton.test.tsx`（新建） | loading state、错误处理 |

### 关键：双 renderer parity 测试

```python
def test_notification_history_renderer_parity():
    fixture = load_nvda_dashboard_with_fact_bundle()
    notif_md = notification._render_single_stock(fixture)
    hist_md = history_service._generate_single_stock_markdown(fixture)
    assert extract_footnotes(notif_md) == extract_footnotes(hist_md)
    assert extract_action_plan_items(notif_md) == extract_action_plan_items(hist_md)
```

### LLM mock 模式

参考现有 `tests/test_action_plan_renderer.py` 模式：构造 dashboard fixture，驱动 sanitizer + renderer，断言输出。不调真 LLM。

### 不改的测试

- `test_portfolio_context_service.py` — service 层接口不变
- `test_market_analyzer_generate_text.py` — 大盘复盘不动
- 既有 ReportNews / ReportOverview / ReportDetails 测试

### CI 路径

| Phase | 触发的 CI Gate |
|---|---|
| 1, 2 | backend-gate + ai-governance |
| 3 | backend-gate + ai-governance |
| 4 | backend-gate + ai-governance + web-gate |
| 5 | backend-gate + ai-governance + web-gate + docker-build |
| 6 | 全部 |

---

## Section E — 实施阶段

按 [[feedback-phase-commit-gating]] 用户逐 phase gate，每个 phase 一个 PR。

| Phase | 标题 | 大致行数 | 风险 | 用户可见变化 |
|---|---|---|---|---|
| **1** | 基础设施：FactBundle + facts_builder + 类型 | ~600 | 低（纯新增） | 无 — fact_bundle 挂在 dashboard 但前端不消费 |
| **2** | LLM 改造：prompt + sanitizer + 候选合成 | ~500 | 中（改 LLM 决策路径） | 新分析的 action_plan 用真实技术位，UI 还是旧 |
| **3** | 后端渲染：notification + history 脚注 | ~300 | 低（带 fallback） | 通知/markdown 报告里出现脚注 |
| **4** | 前端基建：hook + atomic 组件 + quote endpoint | ~400 | 低（新代码未挂载） | 无 — 组件准备好但未替换 |
| **5** | 前端集成：4 大 section 落地 + 删除旧组件 | ~800 | 高（可见 UI 大改） | 报告页全面升级 |
| **6** | 收尾：feature flag 移除 + 文档 + 边缘场景 | ~100 | 低 | 无 |

**总计 ~2700 行净改动跨 6 个 PR**。

### Phase 间依赖

```
Phase 1 ─┬─> Phase 2 ──> Phase 3 ──┐
         │                          │
         └─> Phase 4 ───────────────┴──> Phase 5 ──> Phase 6
```

Phase 2 和 Phase 4 不互相依赖，可并行。

### Feature Flag

Phase 2-5 期间用环境变量 `STRUCTURED_EVIDENCE_V1=true` 作为 opt-in 开关：
- `false`（默认）：走老路径，零回归
- `true`：启用新决策 + 新渲染
- Phase 6 删 flag、新路径成默认

### 不能并行的工作

per [[repo-dual-renderers]]：Phase 3 中 `notification.py` 与 `history_service.py` 同区域改动必须**串行提交**（同一 PR 内串行写，避免 merge 冲突）。

### 每个 PR 的描述模板

按 `.github/PULL_REQUEST_TEMPLATE.md`：
- 改了什么
- 为什么这么改（指向本 spec 的 Section X）
- 验证情况（pytest + npm build 结果）
- 风险点 + 回滚（关 feature flag）

---

## 向后兼容

### 老分析记录

- 无 `fact_bundle` / 无 `evidence_refs` → renderer 回退到当前展示（不动 `2026-05-16-action-plan-items-design.md` 已落地的渲染逻辑）
- `strategy_thesis` 是 `string` 形态（旧）vs `object` 形态（新）→ 渲染层均能消费
- `action_plan_items` 缺新字段 → renderer 不渲染脚注，按当前格式输出

### 前端

- `EvidenceExpansion` 收到空 refs → 不渲染该区域
- `PriceMapCard` 缺 fact_bundle → 回退到 `battle_plan.sniper_points` + 现价（简化版）
- `StrategyHeroCard` 缺 evidence_refs → 只显示 thesis 文本，无 citation pill

### 不需要回填

历史 `analysis_history` 不重跑、不回填 — 老报告以老形态呈现是可接受的。

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| facts_builder 计算复杂度高、性能下降 | 单元测试卡 P95 < 500ms；缓存 ATR / Fib 计算结果（同次分析复用） |
| 新 prompt 把 LLM 搞糊涂、输出更差 | Phase 2 上线时打开 feature flag 灰度，跑 A/B 对比 |
| Sanitizer 太严格，把好 LLM 输出全清零 | 每次清零自动 log + 触发兜底；Phase 2 加监控指标 `sanitizer_rejection_rate` |
| Tier-2 兜底覆盖率太高 → "都是代码合成的" 的反向问题 | UI 的"🤖 代码兜底"徽章透明展示；后续 LLM 提示词迭代 |
| 双 renderer 发散 | parity 测试 + Phase 3 PR 内必须同时改两份 |
| 实时报价 endpoint 被刷爆 | 限流 60 req/min/IP + 1s 单 code 缓存 |
| Token 预算超限 | 字段紧凑表 + 仅注入 LLM 当前阶段需要的 facts（strategy classify 不需要 sentiment_dimensions 全量） |
| qlib 模型不更新 | facts_builder 检测 `quant_models/<market>/<week>` 时间戳，超过 4 周时给 fact 加 `confidence: 0.1` |
| 前端组件改动量大、回归风险 | Phase 4 atomic 组件先单测覆盖；Phase 5 加 e2e playwright 测一个 NVDA 完整报告 |
| 用户已习惯老 UI、不喜欢新设计 | Phase 6 之前保留 feature flag，可一键回退 |
| Frontend 留白不够 / 拥挤（用户硬性要求） | Phase 5 PR 必须附 screenshot；review 时人眼对照 visual companion mockup 检查 |

---

## 非目标（重申）

- 实时订单执行 / 券商 API 对接
- 历史回测验证建议
- 重做 committee 内部架构
- 引入新 LLM 提供商
- 全实时价格（用混合模式即可）
- 桌面端组件 mirror（本 spec 完成后另立 initiative 单独考虑）
- 历史分析数据回填

---

## 附：相关文件路径速查

**新建**
- `src/analysis/__init__.py`
- `src/analysis/facts.py`（FactRecord / FactBundle / CandidateLevel 定义）
- `src/analysis/facts_builder.py`
- `src/analysis/candidate_rules.py`（20 条规则实现）
- `api/v1/endpoints/quote.py`
- `apps/dsa-web/src/hooks/useFactBundle.ts`
- `apps/dsa-web/src/components/report/PriceMapCard.tsx`
- `apps/dsa-web/src/components/report/EvidenceExpansion.tsx`
- `apps/dsa-web/src/components/report/EvidenceRef.tsx`
- `apps/dsa-web/src/components/report/StrategyHeroCard.tsx`
- `apps/dsa-web/src/components/report/PositionFlowTimeline.tsx`
- `apps/dsa-web/src/components/report/RefreshPriceButton.tsx`
- `tests/test_facts_builder.py`
- `tests/test_candidate_levels.py`
- `tests/test_sanitizer_v2.py`
- `tests/test_synthesize_from_candidates.py`
- `tests/test_evidence_renderer.py`
- `tests/test_quote_endpoint.py`

**修改**
- `src/analyzer.py`（prompt 重写 + sanitizer 重写）
- `src/pipeline.py`（fact_bundle 装配挂到 dashboard）
- `src/orchestrator.py`（与 facts_builder 接口）
- `src/services/portfolio_context_service.py`（synthesize 函数重写）
- `src/notification.py`（脚注渲染）
- `src/services/history_service.py`（镜像脚注渲染）
- `api/v1/router.py`（注册 quote endpoint）
- `apps/dsa-web/src/types/analysis.ts`（类型扩展）
- `apps/dsa-web/src/components/report/ActionPlanTable.tsx`（重写）
- `apps/dsa-web/src/components/report/ReportSummary.tsx`（重排 4 section）

**删除**
- `apps/dsa-web/src/components/report/StrategySelector.tsx`
- `apps/dsa-web/src/components/report/StrategyThesis.tsx`
- `apps/dsa-web/src/components/report/PositionOutcomeSummary.tsx`

---

## 交付分工建议（给 writing-plans）

按 6 个 phase 各自独立 PR，writing-plans 时按以下拆分细化任务：

1. **Phase 1 任务**：FactRecord / FactBundle / CandidateLevel 类型定义 → facts_builder 核心逻辑 → 8 个 type 各自的 fetcher（technical / quant / committee / intel / portfolio / flow / chip / candidate）→ 单元测试 → pipeline 集成
2. **Phase 2 任务**：candidate_rules.py 20 条规则实现 → analyzer prompt 重写 → sanitizer v2 9 条规则 → synthesizer 重写 → 测试
3. **Phase 3 任务**：notification.py 脚注渲染 → history_service.py 镜像渲染 → parity 测试 → backward compat 测试
4. **Phase 4 任务**：useFactBundle hook → atomic 组件（EvidenceRef / EvidenceExpansion / RefreshPriceButton）→ quote endpoint → 单元测试
5. **Phase 5 任务**：PriceMapCard / StrategyHeroCard / PositionFlowTimeline 实现 → ActionPlanTable 重写 → ReportSummary 重排 → 删除旧组件 → e2e 测试
6. **Phase 6 任务**：feature flag 移除 → 文档更新 → CHANGELOG.md → 边缘场景修复
