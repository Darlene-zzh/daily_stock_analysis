"""[[repo-dual-renderers]] guard: notification.py and history_service.py both
render the same action_plan + footnote block from the same dashboard input.
The two renderers MUST produce byte-equal action_plan + footnote sections.
"""
import json
from pathlib import Path

from src.notification import _render_action_plan_items as notif_render
from src.notification import _render_evidence_footnotes as notif_footnotes
from src.services.history_service import _render_action_plan_items as hist_render
from src.services.history_service import _render_evidence_footnotes as hist_footnotes


FIXTURE = Path(__file__).parent / "fixtures" / "nvda_dashboard_phase3.json"


def test_action_plan_section_byte_equal():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]

    notif_lines = notif_render(items, fact_bundle=bundle)
    hist_lines = hist_render(items, fact_bundle=bundle)
    assert notif_lines == hist_lines, (
        "notification.py vs history_service.py action_plan output diverged"
    )


def test_footnote_section_byte_equal():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]

    refs: list = []
    for it in items[:4]:
        for r in (it.get("evidence_refs") or []):
            if isinstance(r, str) and r and r not in refs:
                refs.append(r)

    notif_fn = notif_footnotes(refs, bundle)
    hist_fn = hist_footnotes(refs, bundle)
    assert notif_fn == hist_fn, (
        "notification.py vs history_service.py footnote output diverged"
    )


def test_synthesized_badge_appears_in_both():
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    notif_out = "\n".join(notif_render(items, fact_bundle=bundle))
    hist_out = "\n".join(hist_render(items, fact_bundle=bundle))
    assert "🤖" in notif_out
    assert "🤖" in hist_out


def test_legacy_item_without_evidence_refs_still_renders():
    """The 3rd fixture item has no evidence_refs — must still render its
    trigger price line in both renderers (no superscripts attached)."""
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    notif_out = "\n".join(notif_render(items, fact_bundle=bundle))
    hist_out = "\n".join(hist_render(items, fact_bundle=bundle))
    assert "230.00" in notif_out
    assert "230.00" in hist_out


# ---------------------------------------------------------------------------
# Inline superscript ↔ footnote number alignment
# ---------------------------------------------------------------------------
# The two renderers use INDEPENDENT counters:
#   * `_render_action_plan_items` assigns inline superscripts via `_num_for`
#     (counter starts at 1, advances on first sight)
#   * `_render_evidence_footnotes` assigns footnote numbers by `collected_refs`
#     insertion order (also 1..N)
#
# If these two counters disagree, the user sees "触发² ... ¹ `[technical.X]`"
# style mismatches — clicking ² in the body would land on the wrong fact.
# This guard catches that drift on the NVDA fixture.

_SUP_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUP_TO_INT = {c: i for i, c in enumerate(_SUP_CHARS)}


def _parse_leading_sup(line: str):
    """Footnote lines start with ¹ / ² / ... Parse the leading superscript int."""
    n, i = 0, 0
    while i < len(line) and line[i] in _SUP_TO_INT:
        n = n * 10 + _SUP_TO_INT[line[i]]
        i += 1
    return n if i > 0 else None


def _parse_trailing_sup(line: str):
    """Body lines end with the inline superscript ref. Parse trailing int."""
    chars = []
    for c in reversed(line):
        if c in _SUP_TO_INT:
            chars.append(c)
        else:
            break
    if not chars:
        return None
    n = 0
    for c in reversed(chars):
        n = n * 10 + _SUP_TO_INT[c]
    return n


def _footnote_id_by_number(footnote_lines: list) -> dict:
    """Build {1: fact_id, 2: fact_id, ...} from footnote block lines."""
    fn_map: dict = {}
    for line in footnote_lines:
        if not line or line[0] not in _SUP_TO_INT:
            continue
        n = _parse_leading_sup(line)
        if n is None:
            continue
        m = line.find("`[")
        if m == -1:
            continue
        end = line.find("]`", m)
        if end == -1:
            continue
        fn_map[n] = line[m + 2:end]
    return fn_map


def _collected_refs(items: list) -> list:
    """Mirror the caller-side collection (insertion-order dedup over items[:4])."""
    collected: list = []
    for it in items[:4]:
        for r in (it.get("evidence_refs") or []):
            if isinstance(r, str) and r and r not in collected:
                collected.append(r)
    return collected


def _assert_inline_matches_footnote(render_body, render_footnote, items, bundle):
    """Render both blocks; assert every inline superscript on item 0's
    触发/技术面/基本面/量化 lines points to the fact_id implied by item 0's
    `evidence_refs` ordering. Item 0 in fixture has both `quant.qlib_rank`
    AND `committee.pm_verdict` — the classic root cause of the orphan drift."""
    body_lines = render_body(items, fact_bundle=bundle)
    fn_lines = render_footnote(_collected_refs(items), bundle)
    fn_map = _footnote_id_by_number(fn_lines)

    # Slice item 0's body (between ① and ② markers)
    i0_start = next(i for i, l in enumerate(body_lines) if "①" in l)
    i0_end = next(
        (i for i, l in enumerate(body_lines[i0_start + 1:], start=i0_start + 1) if "②" in l),
        len(body_lines),
    )
    item0_body = body_lines[i0_start:i0_end]

    item0_refs = items[0].get("evidence_refs") or []
    # Expected mapping per the renderer's slot-assignment contract:
    #   触发 → refs[0]
    #   技术面 → first remaining technical.*
    #   基本面 → first remaining intel.*
    #   量化 → first remaining quant.* (falling back to committee.*)
    used = set()
    expected_trigger = item0_refs[0] if item0_refs else None
    if expected_trigger:
        used.add(expected_trigger)

    def _pick(prefix):
        for r in item0_refs:
            if r.startswith(prefix) and r not in used:
                used.add(r)
                return r
        return None

    expected_tech = _pick("technical.")
    expected_fund = _pick("intel.")
    expected_quant = _pick("quant.") or _pick("committee.")

    line_to_expected = {
        "**触发**": expected_trigger,
        "**技术面**": expected_tech,
        "**基本面**": expected_fund,
        "**量化**": expected_quant,
    }

    for marker, expected_fact in line_to_expected.items():
        if expected_fact is None:
            continue
        line = next((l for l in item0_body if marker in l), None)
        if line is None:
            continue  # Field absent in this item (e.g., no fundamental_basis)
        sup = _parse_trailing_sup(line)
        assert sup is not None, f"{marker} line has no superscript: {line!r}"
        actual_fact = fn_map.get(sup)
        assert actual_fact == expected_fact, (
            f"{marker} line shows superscript {sup} pointing to footnote "
            f"{actual_fact!r}, but should point to {expected_fact!r} "
            f"(line: {line!r}; fn_map: {fn_map})"
        )


def test_notification_inline_superscripts_align_with_footnote_numbers():
    """Notification renderer: inline ¹²³ on item 0 lines must match the
    footnote block's ¹²³ pointers. Regression guard for the
    pre-registration-order bug found in PR #11 review.
    """
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    _assert_inline_matches_footnote(notif_render, notif_footnotes, items, bundle)


def test_history_inline_superscripts_align_with_footnote_numbers():
    """History renderer: same alignment invariant as notification.py."""
    dashboard = json.loads(FIXTURE.read_text())
    items = dashboard["core_conclusion"]["action_plan_items"]
    bundle = dashboard["fact_bundle"]
    _assert_inline_matches_footnote(hist_render, hist_footnotes, items, bundle)


def test_skipped_trigger_price_item_does_not_leak_refs_to_footnote():
    """When an item has no `trigger_price`, the renderer skips it — its
    evidence_refs must NOT appear in the footnote block (the caller-side
    collected_refs builder must apply the same skip filter, otherwise the
    footnote shows numbered entries with no inline citation in the body).
    """
    # Build a 2-item synthetic input: item 0 renders, item 1 is skipped.
    bundle = {
        "as_of": "2026-05-24T00:00:00Z",
        "market": "us",
        "stock_code": "TEST",
        "facts": [
            {"id": "technical.resistance", "type": "technical", "label": "阻力位",
             "value": 150.0, "display_value": "$150.00"},
            {"id": "technical.skipped_only", "type": "technical", "label": "孤儿事实",
             "value": 999.0, "display_value": "$999.00"},
        ],
        "candidates": [],
    }
    items = [
        {
            "direction": "take_profit",
            "trigger_price": 150.0,
            "trigger_condition": "阻力触及",
            "evidence_refs": ["technical.resistance"],
        },
        {
            "direction": "buy",
            "trigger_price": None,  # skipped by renderer
            "trigger_condition": "应该被跳过",
            "evidence_refs": ["technical.skipped_only"],
        },
    ]

    # Caller-side collected_refs (mirror notification.py / history_service.py
    # logic exactly, including the new skip filter).
    collected_refs: list = []
    for it in items[:4]:
        if not it.get("trigger_price"):
            continue
        for r in (it.get("evidence_refs") or []):
            if isinstance(r, str) and r and r not in collected_refs:
                collected_refs.append(r)

    fn_lines = notif_footnotes(collected_refs, bundle)
    fn_text = "\n".join(fn_lines)
    assert "technical.resistance" in fn_text
    assert "technical.skipped_only" not in fn_text, (
        "Skipped item's evidence_refs must NOT appear in the footnote block"
    )
