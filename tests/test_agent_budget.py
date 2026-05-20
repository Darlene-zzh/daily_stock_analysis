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
