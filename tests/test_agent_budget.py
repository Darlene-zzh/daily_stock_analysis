"""Tests for the committee budget module — timeout resolution + cap."""

from src.agent.budget import DEFAULT_TIMEOUT_S, resolve_timeout_s


def test_default_timeout_is_180_seconds():
    """Default committee wall-clock timeout must be 180s.

    Why: with 4 debate rounds + 4 master fan-outs + retry budget,
    90s was empirically insufficient (see INTC 2026-05-20 incident
    where 3 masters were silently skipped at the deadline break).
    """
    assert DEFAULT_TIMEOUT_S == 180


def test_resolve_timeout_s_defaults_to_180_when_env_absent(monkeypatch):
    monkeypatch.delenv("INVESTMENT_COMMITTEE_TIMEOUT_S", raising=False)
    assert resolve_timeout_s() == 180


def test_resolve_timeout_s_respects_env_override(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_TIMEOUT_S", "300")
    assert resolve_timeout_s() == 300


def test_resolve_timeout_s_falls_back_to_default_on_garbage(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_TIMEOUT_S", "not-a-number")
    assert resolve_timeout_s() == DEFAULT_TIMEOUT_S


def test_resolve_masters_parallel_defaults_to_false(monkeypatch):
    """Default is serial (free-tier safe). Opt-in via env var."""
    monkeypatch.delenv("INVESTMENT_COMMITTEE_MASTERS_PARALLEL", raising=False)
    from src.agent.budget import resolve_masters_parallel
    assert resolve_masters_parallel() is False


def test_resolve_masters_parallel_respects_true_env(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_MASTERS_PARALLEL", "true")
    from src.agent.budget import resolve_masters_parallel
    assert resolve_masters_parallel() is True


def test_resolve_masters_parallel_treats_garbage_as_false(monkeypatch):
    monkeypatch.setenv("INVESTMENT_COMMITTEE_MASTERS_PARALLEL", "maybe")
    from src.agent.budget import resolve_masters_parallel
    assert resolve_masters_parallel() is False


def test_llm_call_budget_acquire_is_thread_safe():
    """LLMCallBudget.acquire must be thread-safe — parallel master
    fan-out (INVESTMENT_COMMITTEE_MASTERS_PARALLEL=true) calls
    acquire from 4 threads concurrently.
    """
    from concurrent.futures import ThreadPoolExecutor
    from src.agent.budget import LLMCallBudget

    budget = LLMCallBudget(cap=100)

    def grab(_):
        return budget.acquire("master_x")

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(grab, range(100)))

    assert all(results), f"some acquires lost the race: {results.count(False)}"
    assert budget.used == 100, f"used={budget.used} expected 100"
