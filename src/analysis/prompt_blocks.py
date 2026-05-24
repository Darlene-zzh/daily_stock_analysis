"""Pure formatters for Phase 2 LLM prompt blocks: facts table, candidates menu,
output contract.

These functions emit deterministic Markdown the LLM consumes. No I/O, no LLM,
no logging — they read a FactBundle and return a string.
"""
from __future__ import annotations

from typing import Optional

from src.analysis.facts import FactBundle, CandidateLevel

# Fixed display order. Types not in this list are appended in stable order.
_TYPE_ORDER = ("technical", "quant", "committee", "intel", "portfolio", "flow", "chip")


def format_facts_table(bundle: FactBundle) -> str:
    """Compact one-line-per-fact block, grouped by type in fixed order.

    Each line: `<id> · <label> = <display_value> [extra hints]`

    The id is left exposed so the LLM can cite it in evidence_refs.
    """
    lines: list[str] = ["## [事实数据库]"]
    if not bundle.facts:
        lines.append("（无可用事实）")
        return "\n".join(lines)

    by_type: dict[str, list] = {}
    for f in bundle.facts:
        by_type.setdefault(f.type, []).append(f)

    ordered_types = list(_TYPE_ORDER) + [t for t in by_type if t not in _TYPE_ORDER]
    for type_name in ordered_types:
        items = by_type.get(type_name) or []
        if not items:
            continue
        lines.append(f"\n### {type_name}")
        for f in items:
            extras = []
            if isinstance(f.extra, dict):
                for k in ("zone", "role", "severity", "is_dissent", "interpretation"):
                    v = f.extra.get(k)
                    if v not in (None, "", False):
                        extras.append(f"{k}={v}")
            extra_str = f"  [{', '.join(extras)}]" if extras else ""
            lines.append(f"- `{f.id}` · {f.label} = {f.display_value}{extra_str}")

    return "\n".join(lines)


def format_candidates_menu(
    bundle: FactBundle,
    strategy: Optional[str] = None,
) -> str:
    """Markdown table of candidate trigger prices. LLM must pick `candidate_id`
    from this list — `tier=filtered` rows are excluded, and when `strategy` is
    given, only candidates whose `applicable_strategies` contains it are shown.
    """
    visible: list[CandidateLevel] = [
        c for c in bundle.candidates
        if c.tier != "filtered"
        and (strategy is None or strategy in c.applicable_strategies)
    ]
    lines: list[str] = ["## [候选触发价位] — 你只能从下表选 candidate_id，禁止创造新价位"]
    if not visible:
        lines.append("（无可用候选）")
        return "\n".join(lines)

    lines.append("")
    lines.append("| ID | 方向 | 价格 | 距现价 | 规则 | 适用策略 | 层级 |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in visible:
        dist = f"{c.distance_pct_from_current:+.1f}%"
        strategies = ", ".join(c.applicable_strategies)
        lines.append(
            f"| `{c.id}` | {c.direction} | {c.display_value} | {dist} "
            f"| {c.basis_rule} | {strategies} | {c.tier} |"
        )
    return "\n".join(lines)


OUTPUT_CONTRACT_ZH = """## [输出契约 — Phase 2 证据接地]

对推荐策略输出 2-4 条 action_plan_items。**每条必须包含以下新字段**：

- `candidate_id`: 上表某个 ID（不能是 filtered 的，也不能凭空创造）
- `trigger_price`: 必须等于该 candidate 的 price（系统会强制核对）
- `evidence_refs`: 至少 2 个 fact_id，引用支持决策的事实（来自上方事实数据库）
- `narrative`: 一段论证文本（30-80 字），可在文中内嵌 `<ref:fact_id>` 标记
- `tier`: `primary` 或 `discipline_anchor`，与上表的 tier 保持一致
- `provenance`: 固定填 `"llm"`

其余字段（trigger_condition / direction / shares / pct_of_position / pct_of_equity /
technical_basis / fundamental_basis / quant_signal / invalidation_rule / priority）按现有约束保留。

**硬约束：**
- `discipline_anchor` 层至多 1 条（仅当没有任何合适的 primary 时使用）
- 同一 `candidate_id` 不能出现两次
- `direction` 必须与该 candidate 的方向一致
"""
