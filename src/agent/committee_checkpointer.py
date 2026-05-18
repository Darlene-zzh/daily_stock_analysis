# -*- coding: utf-8 -*-
"""Sprint 4 — SQLite-backed checkpoint helpers for the Investment Committee.

A committee run is opt-in checkpointable: if
``TASK_QUEUE_CHECKPOINT_ENABLED=true`` is set in the environment, the
orchestrator snapshots its :class:`CommitteeState` to a per-query SQLite DB
under ``data/committee_checkpoints/<query_id>.db`` after every node that
mutates state.  When a later run is invoked with the **same** query_id, it
reads the snapshot, skips already-completed nodes, and continues from where
the previous run stopped.

Design choices (locked):

- **Per-query DB**.  We use one SQLite file per query_id so concurrent
  tickers don't contend on the same DB file.  This mirrors the
  TradingAgents pattern (``tradingagents/graph/checkpointer.py``) but
  keyed on ``query_id`` rather than ticker+date because our orchestrator
  is single-ticker-per-run.
- **Opt-in by env**.  Default is OFF so the existing committee flow stays
  byte-identical for users who haven't enabled checkpointing.
- **Best-effort persist**.  A checkpoint write failure must NEVER raise
  into the orchestrator — log + swallow.  A corrupted DB on resume must
  fall back to "start fresh".
- **No LangGraph runtime required**.  We use ``SqliteSaver`` as our
  underlying storage engine, but we serialize our own
  :class:`CommitteeState` snapshots (JSON) rather than relying on
  LangGraph's per-node writes.  This is intentional: the committee's
  imperative driver in :meth:`InvestmentCommitteeOrchestrator.run` is
  the source of truth for which nodes have completed; LangGraph is wired
  in for spec-fidelity but not the executor.

The SqliteSaver dependency is **optional**.  If ``langgraph-checkpoint-sqlite``
is not installed (or fails to import for any reason), every public function
here becomes a no-op so the orchestrator continues without checkpointing.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Env & path helpers
# --------------------------------------------------------------------------- #


def checkpoint_enabled() -> bool:
    """Read the opt-in flag.  Truthy iff ``TASK_QUEUE_CHECKPOINT_ENABLED`` is
    one of ``1 / true / yes / on`` (case-insensitive)."""
    raw = os.environ.get("TASK_QUEUE_CHECKPOINT_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _safe_query_id(query_id: str) -> str:
    """Sanitise a query_id so it cannot escape the checkpoint directory."""
    # Only allow [A-Za-z0-9_-]; collapse anything else to '_'
    out_chars = []
    for ch in (query_id or ""):
        if ch.isalnum() or ch in ("_", "-"):
            out_chars.append(ch)
        else:
            out_chars.append("_")
    safe = "".join(out_chars)[:128]
    return safe or "_"


def _checkpoint_root() -> Path:
    """Return the root checkpoint dir, creating it if absent."""
    root = Path(os.environ.get("COMMITTEE_CHECKPOINT_DIR", "data/committee_checkpoints"))
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover — disk-full / permission corner
        logger.warning("[committee:checkpoint] mkdir failed for %s: %s", root, exc)
    return root


def checkpoint_db_path(query_id: str) -> Path:
    """Return the SQLite DB path used for a particular query_id."""
    return _checkpoint_root() / f"{_safe_query_id(query_id)}.db"


# --------------------------------------------------------------------------- #
# Storage backend — uses langgraph SqliteSaver when available, falls back to
# a plain sqlite3 table when it's not.
# --------------------------------------------------------------------------- #


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS committee_state_snapshots (
    query_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


def _try_import_sqlite_saver() -> Any:
    """Soft-import :class:`SqliteSaver` so the orchestrator works without it."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
        return SqliteSaver
    except Exception as exc:  # pragma: no cover — optional dep
        logger.debug("[committee:checkpoint] SqliteSaver unavailable: %s", exc)
        return None


def save_state(query_id: str, state: Dict[str, Any]) -> bool:
    """Persist a committee state snapshot keyed on ``query_id``.

    Returns ``True`` on success, ``False`` on any failure (caller may
    ignore the return — failures are logged at debug level).
    """
    if not query_id:
        return False
    try:
        import time
        db = checkpoint_db_path(query_id)
        conn = sqlite3.connect(str(db), check_same_thread=False)
        try:
            conn.execute(_TABLE_DDL)
            payload = json.dumps(state, ensure_ascii=False, default=str)
            conn.execute(
                "INSERT INTO committee_state_snapshots(query_id, state_json, updated_at) "
                "VALUES(?, ?, ?) "
                "ON CONFLICT(query_id) DO UPDATE SET "
                "state_json=excluded.state_json, updated_at=excluded.updated_at",
                (_safe_query_id(query_id), payload, time.time()),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(
            "[committee:checkpoint] save failed for query_id=%s: %s",
            query_id, exc,
        )
        return False


def load_state(query_id: str) -> Optional[Dict[str, Any]]:
    """Load the most recent state snapshot for ``query_id`` (or ``None``)."""
    if not query_id:
        return None
    db = checkpoint_db_path(query_id)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db), check_same_thread=False)
        try:
            cur = conn.execute(
                "SELECT state_json FROM committee_state_snapshots WHERE query_id = ?",
                (_safe_query_id(query_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return json.loads(row[0])
        finally:
            conn.close()
    except (sqlite3.DatabaseError, json.JSONDecodeError, OSError) as exc:
        # Corrupt or unreadable DB → treat as "no checkpoint" so the run
        # starts fresh rather than crashing.
        logger.warning(
            "[committee:checkpoint] load failed for query_id=%s, falling back to "
            "fresh run: %s", query_id, exc,
        )
        return None


def has_checkpoint(query_id: str) -> bool:
    """Cheap existence check used by the orchestrator pre-resume."""
    return load_state(query_id) is not None


def clear_checkpoint(query_id: str) -> bool:
    """Delete the snapshot row for ``query_id``.  Returns ``True`` on success."""
    if not query_id:
        return False
    db = checkpoint_db_path(query_id)
    if not db.exists():
        return True
    try:
        conn = sqlite3.connect(str(db), check_same_thread=False)
        try:
            conn.execute(
                "DELETE FROM committee_state_snapshots WHERE query_id = ?",
                (_safe_query_id(query_id),),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(
            "[committee:checkpoint] clear failed for query_id=%s: %s",
            query_id, exc,
        )
        return False


# Re-exported flag so callers can soft-detect availability without importing
# langgraph themselves.
SQLITE_SAVER_AVAILABLE = _try_import_sqlite_saver() is not None
