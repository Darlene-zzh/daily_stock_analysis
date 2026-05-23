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
