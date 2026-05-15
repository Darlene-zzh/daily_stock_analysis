# -*- coding: utf-8 -*-
"""Portfolio CSV import service with extensible parser registry."""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data_provider.base import canonical_stock_code
from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import (
    PortfolioBusyError,
    PortfolioConflictError,
    PortfolioOversellError,
    PortfolioService,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CsvParserSpec:
    """CSV parser specification for one broker."""

    broker: str
    aliases: Tuple[str, ...]
    display_name: str
    column_hints: Dict[str, Tuple[str, ...]]
    cash_event_action_map: Dict[str, str] = field(default_factory=dict)


DEFAULT_PARSER_SPECS: Tuple[CsvParserSpec, ...] = (
    CsvParserSpec(
        broker="huatai",
        aliases=(),
        display_name="华泰",
        column_hints={
            "trade_date": ("成交日期", "成交时间", "发生日期", "日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("买卖标志", "买卖方向", "操作"),
            "quantity": ("成交数量", "数量", "成交股数"),
            "price": ("成交均价", "成交价格", "价格", "成交价", "均价"),
            "trade_uid": ("成交编号", "成交序号", "流水号"),
        },
    ),
    CsvParserSpec(
        broker="citic",
        aliases=("zhongxin",),
        display_name="中信",
        column_hints={
            "trade_date": ("发生日期", "成交日期", "日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("买卖方向", "买卖标志", "业务名称"),
            "quantity": ("成交数量", "数量", "成交股数"),
            "price": ("成交价格", "成交均价", "价格", "成交价"),
            "trade_uid": ("合同编号", "成交编号", "委托编号"),
        },
    ),
    CsvParserSpec(
        broker="cmb",
        aliases=("zhaoshang", "cmbchina"),
        display_name="招商",
        column_hints={
            "trade_date": ("日期", "成交日期", "发生日期"),
            "symbol": ("证券代码", "股票代码", "代码"),
            "side": ("交易方向", "买卖方向", "买卖标志"),
            "quantity": ("成交股数", "成交数量", "数量"),
            "price": ("成交价", "成交价格", "成交均价", "均价"),
            "trade_uid": ("流水号", "成交编号", "成交序号"),
        },
    ),
    CsvParserSpec(
        broker="trading212",
        aliases=("t212", "trading_212"),
        display_name="Trading 212",
        column_hints={
            "trade_date": ("Time",),
            "symbol": ("Ticker",),
            "side": ("Action",),
            "quantity": ("No. of shares",),
            "price": ("Price / share",),
            "trade_uid": ("ID",),
        },
        cash_event_action_map={
            "deposit": "deposit",
            "interest on cash": "interest",
            "dividend (dividend)": "dividend",
            "spending cashback": "cashback",
            "card debit": "card_debit",
        },
    ),
)


class PortfolioImportService:
    """Parse broker CSV and commit normalized trade records with dedup."""
    _shared_parser_registry: Dict[str, CsvParserSpec] = {}
    _shared_broker_alias_map: Dict[str, str] = {}
    _shared_registry_initialized: bool = False

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        repo: Optional[PortfolioRepository] = None,
    ):
        self.portfolio_service = portfolio_service or PortfolioService()
        self.repo = repo or PortfolioRepository()
        self._parser_registry = self.__class__._shared_parser_registry
        self._broker_alias_map = self.__class__._shared_broker_alias_map
        if not self.__class__._shared_registry_initialized:
            self._init_default_parsers()
            self.__class__._shared_registry_initialized = True

    def _init_default_parsers(self) -> None:
        for spec in DEFAULT_PARSER_SPECS:
            self.register_parser(spec)

    def register_parser(self, spec: CsvParserSpec) -> None:
        """Register or replace one broker parser spec."""
        broker = (spec.broker or "").strip().lower()
        if not broker:
            raise ValueError("broker is required")
        new_aliases = tuple(sorted({alias.strip().lower() for alias in spec.aliases if alias}))
        for alias in new_aliases:
            if alias == broker:
                raise ValueError(f"alias '{alias}' cannot be the same as broker id")
            existing_target = self._broker_alias_map.get(alias)
            if existing_target and existing_target != broker:
                raise ValueError(
                    f"alias '{alias}' already registered by broker '{existing_target}'"
                )
        for alias, target in list(self._broker_alias_map.items()):
            if target == broker and alias not in new_aliases:
                self._broker_alias_map.pop(alias, None)
        self._parser_registry[broker] = CsvParserSpec(
            broker=broker,
            aliases=new_aliases,
            display_name=spec.display_name or broker,
            column_hints=dict(spec.column_hints or {}),
            cash_event_action_map={
                str(action_text).strip().lower(): str(kind).strip().lower()
                for action_text, kind in (spec.cash_event_action_map or {}).items()
                if str(kind).strip()
            },
        )
        for alias in self._parser_registry[broker].aliases:
            self._broker_alias_map[alias] = broker

    def list_supported_brokers(self) -> List[Dict[str, Any]]:
        """List canonical broker ids and aliases for frontend selector."""
        items: List[Dict[str, Any]] = []
        for broker in sorted(self._parser_registry.keys()):
            aliases = sorted(alias for alias, target in self._broker_alias_map.items() if target == broker)
            items.append(
                {
                    "broker": broker,
                    "aliases": aliases,
                    "display_name": self._parser_registry[broker].display_name,
                }
            )
        return items

    def parse_trade_csv(
        self,
        *,
        broker: str,
        content: bytes,
    ) -> Dict[str, Any]:
        broker_norm = self._normalize_broker(broker)
        parser_spec = self._parser_registry[broker_norm]
        df = self._read_csv(content)

        records: List[Dict[str, Any]] = []
        cash_events: List[Dict[str, Any]] = []
        skipped = 0
        errors: List[str] = []

        for idx, row in df.iterrows():
            normalized = self._normalize_trade_row(row=row, parser_spec=parser_spec)
            if normalized is not None:
                try:
                    # Keep a stable line-level marker so repeated imports of the same
                    # file remain idempotent, while identical split fills on separate
                    # CSV lines do not collapse into one dedup key.
                    normalized["_source_line_number"] = int(idx) + 2
                    normalized["dedup_hash"] = self._build_dedup_hash(normalized)
                    records.append(normalized)
                except Exception as exc:  # pragma: no cover - defensive path
                    skipped += 1
                    errors.append(f"row={idx + 1}: {exc}")
                continue

            cash_event = self._normalize_cash_row(row=row, parser_spec=parser_spec)
            if cash_event is not None:
                cash_event["_source_line_number"] = int(idx) + 2
                cash_events.append(cash_event)
                continue

            skipped += 1

        return {
            "broker": broker_norm,
            "record_count": len(records),
            "skipped_count": skipped,
            "error_count": len(errors),
            "records": records,
            "cash_events": cash_events,
            "errors": errors[:20],
        }

    def commit_trade_records(
        self,
        *,
        account_id: int,
        broker: str,
        records: List[Dict[str, Any]],
        cash_events: Optional[List[Dict[str, Any]]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        broker_norm = self._normalize_broker(broker)

        inserted_count = 0
        duplicate_count = 0
        failed_count = 0
        errors: List[str] = []
        seen_trade_uids: set[str] = set()
        seen_dedup_hashes: set[str] = set()

        inserted_cash_count = 0
        duplicate_cash_count = 0
        failed_cash_count = 0
        seen_cash_notes: set[str] = set()

        for i, record in enumerate(records):
            try:
                trade_uid = (record.get("trade_uid") or "").strip() or None
                dedup_hash = (record.get("dedup_hash") or "").strip()
                if not dedup_hash:
                    dedup_hash = self._build_dedup_hash(record)

                if trade_uid and self.repo.has_trade_uid(account_id, trade_uid):
                    duplicate_count += 1
                    continue
                dedup_hash_to_use: Optional[str] = dedup_hash or None
                if dedup_hash_to_use and self.repo.has_trade_dedup_hash(account_id, dedup_hash_to_use):
                    duplicate_count += 1
                    continue

                if dry_run:
                    if trade_uid and trade_uid in seen_trade_uids:
                        duplicate_count += 1
                        continue
                    if dedup_hash_to_use and dedup_hash_to_use in seen_dedup_hashes:
                        duplicate_count += 1
                        continue
                    inserted_count += 1
                    if trade_uid:
                        seen_trade_uids.add(trade_uid)
                    if dedup_hash_to_use:
                        seen_dedup_hashes.add(dedup_hash_to_use)
                    continue

                trade_date_value = record.get("trade_date")
                if isinstance(trade_date_value, date):
                    trade_date_obj = trade_date_value
                else:
                    trade_date_obj = date.fromisoformat(str(trade_date_value))

                self.portfolio_service.record_trade(
                    account_id=account_id,
                    symbol=str(record["symbol"]),
                    trade_date=trade_date_obj,
                    side=str(record["side"]),
                    quantity=float(record["quantity"]),
                    price=float(record["price"]),
                    fee=float(record.get("fee", 0.0) or 0.0),
                    tax=float(record.get("tax", 0.0) or 0.0),
                    market=record.get("market"),
                    currency=record.get("currency"),
                    trade_uid=trade_uid,
                    dedup_hash=dedup_hash_to_use,
                    note=(record.get("note") or "").strip() or f"csv_import:{broker_norm}",
                )
                inserted_count += 1
            except PortfolioConflictError:
                duplicate_count += 1
            except PortfolioOversellError as exc:
                failed_count += 1
                errors.append(f"idx={i}: {exc}")
            except PortfolioBusyError as exc:
                failed_count += 1
                errors.append(f"idx={i}: portfolio_busy: {exc}")
            except Exception as exc:
                failed_count += 1
                errors.append(f"idx={i}: {exc}")

        cash_events_list = list(cash_events or [])
        for idx, event in enumerate(cash_events_list):
            try:
                note = str(event.get("note") or "").strip()
                if not note:
                    failed_cash_count += 1
                    errors.append(f"cash idx={idx}: missing dedup note")
                    continue

                if note in seen_cash_notes:
                    duplicate_cash_count += 1
                    continue

                if self.repo.has_cash_ledger_note(account_id=account_id, note=note):
                    duplicate_cash_count += 1
                    continue

                if dry_run:
                    seen_cash_notes.add(note)
                    inserted_cash_count += 1
                    continue

                event_date_value = event.get("event_date")
                if isinstance(event_date_value, date):
                    event_date_obj = event_date_value
                else:
                    event_date_obj = date.fromisoformat(str(event_date_value))

                self.portfolio_service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date_obj,
                    direction=str(event.get("direction") or "in"),
                    amount=float(event["amount"]),
                    currency=event.get("currency"),
                    note=note,
                )
                seen_cash_notes.add(note)
                inserted_cash_count += 1
            except PortfolioBusyError as exc:
                failed_cash_count += 1
                errors.append(f"cash idx={idx}: portfolio_busy: {exc}")
            except Exception as exc:
                failed_cash_count += 1
                errors.append(f"cash idx={idx}: {exc}")

        return {
            "account_id": account_id,
            "record_count": len(records),
            "inserted_count": inserted_count,
            "duplicate_count": duplicate_count,
            "failed_count": failed_count,
            "cash_event_count": len(cash_events_list),
            "inserted_cash_count": inserted_cash_count,
            "duplicate_cash_count": duplicate_cash_count,
            "failed_cash_count": failed_cash_count,
            "dry_run": bool(dry_run),
            "errors": errors[:20],
        }

    def _normalize_broker(self, value: str) -> str:
        broker = (value or "").strip().lower()
        broker = self._broker_alias_map.get(broker, broker)
        if broker not in self._parser_registry:
            supported = ", ".join(sorted(self._parser_registry.keys()))
            raise ValueError(f"broker must be one of: {supported}")
        return broker

    @staticmethod
    def _read_csv(content: bytes) -> pd.DataFrame:
        for encoding in ("utf-8-sig", "gbk", "gb18030"):
            try:
                return pd.read_csv(
                    io.BytesIO(content),
                    encoding=encoding,
                    dtype=str,
                    keep_default_na=False,
                )
            except UnicodeDecodeError:
                continue
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)

    def _normalize_trade_row(
        self,
        *,
        row: Any,
        parser_spec: CsvParserSpec,
    ) -> Optional[Dict[str, Any]]:
        broker_hints = parser_spec.column_hints

        trade_date_raw = self._pick(
            row,
            *(broker_hints.get("trade_date") or ()),
            "成交日期",
            "发生日期",
            "日期",
            "成交时间",
        )
        trade_date_obj = self._parse_date(trade_date_raw)
        if trade_date_obj is None:
            return None

        symbol_raw = self._pick(
            row,
            *(broker_hints.get("symbol") or ()),
            "证券代码",
            "股票代码",
            "代码",
        )
        symbol = canonical_stock_code(str(symbol_raw or "").strip())
        if not symbol:
            return None

        side_raw = self._pick(
            row,
            *(broker_hints.get("side") or ()),
            "买卖标志",
            "买卖方向",
            "交易方向",
            "业务名称",
            "操作",
        )
        side = self._normalize_side(side_raw)
        if side is None:
            return None

        quantity = self._parse_float(
            self._pick(row, *(broker_hints.get("quantity") or ()), "成交数量", "数量", "成交股数")
        )
        price = self._parse_float(
            self._pick(row, *(broker_hints.get("price") or ()), "成交均价", "成交价格", "价格", "成交价", "均价")
        )
        if quantity is None or quantity <= 0 or price is None or price <= 0:
            return None

        fee = 0.0
        for col in ("手续费", "佣金", "交易费", "规费", "过户费", "Currency conversion fee"):
            value = self._parse_float(self._pick(row, col))
            if value is not None:
                fee += value

        tax = 0.0
        for col in ("印花税", "税费", "其他税费"):
            value = self._parse_float(self._pick(row, col))
            if value is not None:
                tax += value

        trade_uid = self._pick(
            row,
            *(broker_hints.get("trade_uid") or ()),
            "成交编号",
            "成交序号",
            "合同编号",
            "委托编号",
            "流水号",
        )
        currency_raw = self._pick(row, "币种", "货币", "Currency (Price / share)")
        currency = (str(currency_raw).strip().upper() if currency_raw is not None else None) or None

        price_value = float(price)
        if currency == "GBX":
            price_value = price_value / 100.0
            currency = "GBP"

        return {
            "trade_date": trade_date_obj,
            "symbol": symbol,
            "side": side,
            "quantity": float(quantity),
            "price": price_value,
            "fee": float(fee),
            "tax": float(tax),
            "trade_uid": (str(trade_uid).strip() if trade_uid is not None else None) or None,
            "currency": currency,
        }

    def _normalize_cash_row(
        self,
        *,
        row: Any,
        parser_spec: CsvParserSpec,
    ) -> Optional[Dict[str, Any]]:
        """Normalize a CSV row into a cash-ledger event for brokers that map cash actions."""
        action_map = parser_spec.cash_event_action_map or {}
        if not action_map:
            return None

        side_hints = parser_spec.column_hints.get("side") or ()
        action_raw = self._pick(row, *side_hints, "Action")
        action_key = str(action_raw or "").strip().lower()
        kind = action_map.get(action_key)
        if not kind:
            return None

        date_hints = parser_spec.column_hints.get("trade_date") or ()
        event_date_obj = self._parse_date(self._pick(row, *date_hints, "Time"))
        if event_date_obj is None:
            return None

        # Outflow kinds reduce the cash pot (e.g. Trading 212 card debit charged
        # to the same balance that funds trades). All other inflows stay positive.
        direction = "out" if kind == "card_debit" else "in"

        amount_raw = self._parse_float(self._pick(row, "Total"))
        if amount_raw is None:
            return None
        amount = abs(amount_raw)
        if amount <= 0:
            return None

        currency_raw = self._pick(row, "Currency (Total)", "币种", "货币")
        currency = (str(currency_raw).strip().upper() if currency_raw is not None else None) or None

        uid_hints = parser_spec.column_hints.get("trade_uid") or ()
        cash_uid = self._pick(row, *uid_hints, "ID")
        cash_uid_str = (str(cash_uid).strip() if cash_uid is not None else None) or None

        symbol_hints = parser_spec.column_hints.get("symbol") or ()
        symbol_raw = self._pick(row, *symbol_hints, "Ticker")
        symbol = canonical_stock_code(str(symbol_raw or "").strip()) or None

        note_parts: List[str] = [f"csv_import:{parser_spec.broker}", kind]
        if symbol:
            note_parts.append(symbol)
        if cash_uid_str:
            note_parts.append(cash_uid_str)
        dedup_note = ":".join(note_parts)

        return {
            "event_date": event_date_obj,
            "direction": direction,
            "kind": kind,
            "amount": amount,
            "currency": currency,
            "symbol": symbol,
            "cash_uid": cash_uid_str,
            "note": dedup_note,
        }

    @staticmethod
    def _pick(row: Any, *candidates: str) -> Any:
        for name in candidates:
            if name in row.index:
                value = row.get(name)
                if value is not None and str(value).strip() != "" and str(value).strip().lower() != "nan":
                    return value
        return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if not text or text.lower() == "nan":
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()

    @staticmethod
    def _normalize_side(value: Any) -> Optional[str]:
        text = str(value or "").strip().lower()
        if not text:
            return None
        compact = text.replace(" ", "")
        buy_exact = {"buy", "b", "买", "买入", "证券买入", "普通买入"}
        sell_exact = {"sell", "s", "卖", "卖出", "证券卖出", "普通卖出"}
        if compact in buy_exact:
            return "buy"
        if compact in sell_exact:
            return "sell"
        if "买入" in compact or compact.startswith("买"):
            return "buy"
        if "卖出" in compact or compact.startswith("卖"):
            return "sell"
        if compact.endswith("buy"):
            return "buy"
        if compact.endswith("sell"):
            return "sell"
        return None

    @staticmethod
    def _build_dedup_hash(record: Dict[str, Any]) -> str:
        payload = "|".join(
            [
                str(record.get("trade_date") or ""),
                str(record.get("symbol") or ""),
                str(record.get("side") or ""),
                f"{float(record.get('quantity', 0.0)):.8f}",
                f"{float(record.get('price', 0.0)):.8f}",
                f"{float(record.get('fee', 0.0)):.8f}",
                f"{float(record.get('tax', 0.0)):.8f}",
                str(record.get("currency") or ""),
                str(record.get("_source_line_number") or record.get("source_line_number") or ""),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
