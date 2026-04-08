from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .config import AccountPattern


@dataclass(frozen=True)
class MappingRule:
    priority: int
    match_type: str
    pattern: str
    category: str


@dataclass(frozen=True)
class Transaction:
    account: str
    source_file: str
    date: datetime
    amount: Decimal
    payee: str
    memo: str
    raw_text: str
    category: str
    matched_by: str
    mapping_source: str
    include_in_reports: bool
    txn_direction: str
    review_note: str = ""


MANUAL_GUESSES = {
    "GOOGLE CLOUD": ("Internet Subscriptions", "Best guess for cloud/software subscription"),
    "HMRC": ("Utilities & Taxes", "Best guess for tax payment"),
    "STARBUCKS": ("Dining & Food Delivery", "Best guess for coffee shop"),
    "UBER": ("Public Transit", "Best guess for transport"),
    "WHOLE FOODS": ("Groceries & Supplies", "Best guess for grocery merchant"),
}


def normalize(text: str) -> str:
    return " ".join((text or "").split()).upper()


def parse_date(text: str) -> datetime:
    if "/" in text:
        return datetime.strptime(text, "%d/%m/%Y")
    return datetime.strptime(text[:8], "%Y%m%d")


def load_mapping_rules(path: Path) -> list[MappingRule]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rules = [
            MappingRule(
                priority=int(row["Priority"]),
                match_type=row["MatchType"].strip().lower(),
                pattern=row["Pattern"].strip(),
                category=row["Category"].strip(),
            )
            for row in csv.DictReader(handle)
        ]
    return sorted(rules, key=lambda item: (item.priority, len(normalize(item.pattern))), reverse=True)


def parse_qif(path: Path, account: str) -> Iterable[dict]:
    current: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line:
            continue
        if line == "^":
            if current:
                yield {
                    "account": account,
                    "source_file": path.name,
                    "date": parse_date(current.get("D", "")),
                    "amount": Decimal(current.get("T", "0")),
                    "payee": current.get("P", "").strip(),
                    "memo": current.get("M", "").strip(),
                }
            current = {}
            continue
        current[line[0]] = current.get(line[0], "") + line[1:]


def parse_ofx(path: Path, account: str) -> Iterable[dict]:
    text = path.read_text(encoding="cp1252", errors="ignore")
    for block in text.split("<STMTTRN>")[1:]:
        def tag(name: str) -> str:
            match = re.search(fr"<{name}>([^<\r\n]+)", block)
            return match.group(1).strip() if match else ""

        yield {
            "account": account,
            "source_file": path.name,
            "date": parse_date(tag("DTPOSTED")),
            "amount": Decimal(tag("TRNAMT")),
            "payee": tag("NAME"),
            "memo": tag("MEMO"),
        }


def classify(raw_text: str, rules: list[MappingRule]) -> tuple[str, str, str]:
    normalized = normalize(raw_text)
    for rule in rules:
        pattern = normalize(rule.pattern)
        matched = False
        if rule.match_type in {"exact", "equals"}:
            matched = normalized == pattern
        elif rule.match_type == "contains":
            matched = pattern in normalized
        elif rule.match_type == "starts":
            matched = normalized.startswith(pattern)
        elif rule.match_type == "ends":
            matched = normalized.endswith(pattern)
        elif rule.match_type == "regex":
            try:
                matched = bool(re.search(rule.pattern, normalized, re.IGNORECASE))
            except re.error:
                matched = False
        if matched:
            return rule.category, rule.pattern, "mapping"

    for pattern, (category, note) in MANUAL_GUESSES.items():
        if pattern in normalized:
            return category, pattern, note

    return "Miscellaneous", "fallback", "Fallback to Miscellaneous"


def month_sources(month_dir: Path, accounts: tuple[AccountPattern, ...]) -> list[tuple[Path, str]]:
    seen: set[Path] = set()
    sources: list[tuple[Path, str]] = []
    for account in accounts:
        for pattern in account.patterns:
            for path in sorted(month_dir.glob(pattern)):
                if path in seen:
                    continue
                seen.add(path)
                sources.append((path, account.name))
    return sources


def load_transactions(month_dir: Path, mapping_file: Path, accounts: tuple[AccountPattern, ...], year: int, month: int) -> list[Transaction]:
    rules = load_mapping_rules(mapping_file)
    transactions: list[Transaction] = []

    for path, account in month_sources(month_dir, accounts):
        parser = parse_qif if path.suffix.lower() == ".qif" else parse_ofx
        for row in parser(path, account):
            if row["date"].year != year or row["date"].month != month:
                continue

            raw_text = " ".join(part for part in [row["payee"], row["memo"]] if part).strip()
            category, matched_by, mapping_source = classify(raw_text, rules)
            include_in_reports = category != "Transfer"
            txn_direction = "income" if row["amount"] > 0 else "expense"
            review_note = "" if mapping_source == "mapping" else mapping_source

            transactions.append(
                Transaction(
                    account=account,
                    source_file=row["source_file"],
                    date=row["date"],
                    amount=row["amount"],
                    payee=row["payee"],
                    memo=row["memo"],
                    raw_text=raw_text,
                    category=category,
                    matched_by=matched_by,
                    mapping_source=mapping_source,
                    include_in_reports=include_in_reports,
                    txn_direction=txn_direction,
                    review_note=review_note,
                )
            )

    return sorted(transactions, key=lambda item: (item.date, item.account, item.payee, item.amount))
