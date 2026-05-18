# -*- coding: utf-8 -*-
"""Unit tests for ``data_provider/qlib_fetcher.py`` (Sprint 3).

These tests run without qlib installed — every public function MUST
return ``None`` / falsy cleanly when qlib is unavailable.  When qlib is
present we patch its surface so the tests stay deterministic.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

from data_provider import qlib_fetcher


@pytest.fixture(autouse=True)
def reset_init_flag():
    """Each test starts with no prior qlib init."""
    qlib_fetcher._qlib_initialized_region = None
    yield
    qlib_fetcher._qlib_initialized_region = None


# ---------------------------------------------------------------------
# is_supported_market / normalize_to_qlib_symbol
# ---------------------------------------------------------------------

def test_is_supported_market_handles_cn_us_hk():
    assert qlib_fetcher.is_supported_market("cn") is True
    assert qlib_fetcher.is_supported_market("us") is True
    assert qlib_fetcher.is_supported_market("US") is True
    assert qlib_fetcher.is_supported_market("hk") is False
    assert qlib_fetcher.is_supported_market("") is False
    assert qlib_fetcher.is_supported_market(None) is False


def test_normalize_to_qlib_symbol_cn_paths():
    assert qlib_fetcher.normalize_to_qlib_symbol("600519", "cn") == "SH600519"
    assert qlib_fetcher.normalize_to_qlib_symbol("000001", "cn") == "SZ000001"
    assert qlib_fetcher.normalize_to_qlib_symbol("300750", "cn") == "SZ300750"
    assert qlib_fetcher.normalize_to_qlib_symbol("SH600519", "cn") == "SH600519"  # already prefixed
    assert qlib_fetcher.normalize_to_qlib_symbol("832000", "cn") == "BJ832000"
    assert qlib_fetcher.normalize_to_qlib_symbol("99999", "cn") is None  # bad length


def test_normalize_to_qlib_symbol_us_path():
    assert qlib_fetcher.normalize_to_qlib_symbol("aapl", "us") == "AAPL"
    assert qlib_fetcher.normalize_to_qlib_symbol("BRK.B", "us") == "BRK.B"


def test_normalize_to_qlib_symbol_hk_unsupported():
    assert qlib_fetcher.normalize_to_qlib_symbol("hk00700", "hk") is None
    assert qlib_fetcher.normalize_to_qlib_symbol("00700", "hk") is None


# ---------------------------------------------------------------------
# Lazy import + graceful no-op
# ---------------------------------------------------------------------

def test_try_import_qlib_returns_none_when_missing(monkeypatch):
    # Force import to fail even if qlib is installed in dev env.
    monkeypatch.setitem(sys.modules, "qlib", None)
    assert qlib_fetcher._try_import_qlib() is None


def test_ensure_initialized_returns_false_without_qlib(monkeypatch):
    monkeypatch.setattr(qlib_fetcher, "_try_import_qlib", lambda: None)
    assert qlib_fetcher.ensure_initialized("cn") is False


def test_ensure_initialized_returns_false_for_unsupported_market():
    assert qlib_fetcher.ensure_initialized("hk") is False
    assert qlib_fetcher.ensure_initialized("") is False


def test_ensure_initialized_returns_false_when_no_data_dir(monkeypatch, tmp_path):
    """When qlib is importable but provider URI doesn't exist on disk."""
    fake_qlib = types.SimpleNamespace(init=lambda **kw: None)
    monkeypatch.setattr(qlib_fetcher, "_try_import_qlib", lambda: fake_qlib)
    monkeypatch.setenv("QLIB_DATA_DIR", str(tmp_path / "no-such-dir"))
    # Clear region-specific overrides
    monkeypatch.delenv("QLIB_PROVIDER_URI_CN", raising=False)
    assert qlib_fetcher.ensure_initialized("cn") is False


def test_ensure_initialized_succeeds_with_explicit_uri(monkeypatch, tmp_path):
    region_dir = tmp_path / "cn_data"
    region_dir.mkdir()
    init_calls = {}

    def fake_init(*, provider_uri, region):
        init_calls["uri"] = provider_uri
        init_calls["region"] = region

    fake_qlib = types.SimpleNamespace(init=fake_init)
    monkeypatch.setattr(qlib_fetcher, "_try_import_qlib", lambda: fake_qlib)
    monkeypatch.setenv("QLIB_DATA_DIR", str(tmp_path))

    assert qlib_fetcher.ensure_initialized("cn") is True
    assert init_calls["uri"] == str(region_dir)
    assert init_calls["region"] == "cn"

    # Second call should be idempotent — fake_init not called again
    init_calls.clear()
    assert qlib_fetcher.ensure_initialized("cn") is True
    assert init_calls == {}


# ---------------------------------------------------------------------
# get_alpha158_factors graceful failure
# ---------------------------------------------------------------------

def test_get_alpha158_factors_returns_none_without_init(monkeypatch):
    monkeypatch.setattr(qlib_fetcher, "ensure_initialized", lambda region: False)
    assert qlib_fetcher.get_alpha158_factors("SH600519", "cn") is None


def test_get_alpha158_factors_handles_inner_exception(monkeypatch):
    """When qlib raises during D.features we degrade to None, not raise."""
    monkeypatch.setattr(qlib_fetcher, "ensure_initialized", lambda region: True)
    fake_qlib = types.SimpleNamespace()
    monkeypatch.setattr(qlib_fetcher, "_try_import_qlib", lambda: fake_qlib)

    # Inject a fake qlib.data.D module
    fake_data = types.ModuleType("qlib.data")

    class BadD:
        @staticmethod
        def features(*args, **kwargs):
            raise RuntimeError("disk failure")

    fake_data.D = BadD
    monkeypatch.setitem(sys.modules, "qlib.data", fake_data)

    result = qlib_fetcher.get_alpha158_factors("SH600519", "cn")
    assert result is None


# ---------------------------------------------------------------------
# csi300/sp500 universes degrade to empty tuple
# ---------------------------------------------------------------------

def test_csi300_universe_returns_empty_without_qlib(monkeypatch):
    monkeypatch.setattr(qlib_fetcher, "ensure_initialized", lambda region: False)
    assert qlib_fetcher.csi300_universe() == tuple()


def test_sp500_universe_returns_empty_without_qlib(monkeypatch):
    monkeypatch.setattr(qlib_fetcher, "ensure_initialized", lambda region: False)
    assert qlib_fetcher.sp500_universe() == tuple()
