from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from personal_finance.config import load_settings
from personal_finance.ingest import normalize, parse_ofx, parse_qif

from .models import Account, Category, MappingRule, Transaction


@dataclass(frozen=True)
class ParsedUploadTransaction:
    posted_at: datetime
    amount: Decimal
    payee: str
    memo: str
    raw_text: str
    account_name: str
    source_file: str
    matched_by: str
    mapping_source: str
    review_note: str
    dedupe_signature: str
    category_name: str | None


def infer_account_name(path: Path, file_bytes: bytes | None = None) -> str:
    settings = load_settings()
    filename = path.name
    lower_name = filename.lower()
    for account in settings.accounts:
        for pattern in account.patterns:
            if fnmatch.fnmatch(lower_name, pattern.lower()):
                return account.name

    if file_bytes:
        text = file_bytes[:4096].decode("utf-8", errors="ignore").lower()
        if path.suffix.lower() == ".qif":
            return "Amex Credit"
        if "<creditcardmsgsrsv1>" in text or "<ccstmttrnrs>" in text or "<ccacctfrom>" in text:
            return "HSBC Credit"
        if "<bankmsgsrsv1>" in text or "<stmttrnrs>" in text or "<bankacctfrom>" in text:
            return "HSBC Current"

    return "Unassigned Account"


def load_db_mapping_rules(db: Session) -> list[MappingRule]:
    return db.scalars(
        select(MappingRule)
        .options(joinedload(MappingRule.category))
        .order_by(MappingRule.priority.desc(), MappingRule.id.desc())
    ).all()


def classify_from_db_rules(raw_text: str, rules: list[MappingRule]) -> tuple[str | None, str, str]:
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
            return rule.category.name if rule.category else None, rule.pattern, "mapping"
    return None, "", "unmapped"


def parse_uploaded_file(path: Path, db: Session) -> list[ParsedUploadTransaction]:
    suffix = path.suffix.lower()
    if suffix not in {".qif", ".ofx", ".qfx"}:
        return []

    file_bytes = path.read_bytes()
    account_name = infer_account_name(path, file_bytes)
    rows = parse_qif(path, account_name) if suffix == ".qif" else parse_ofx(path, account_name)
    rules = load_db_mapping_rules(db)
    categories = {category.name for category in db.scalars(select(Category)).all()}

    parsed: list[ParsedUploadTransaction] = []
    for row in rows:
        raw_text = " ".join(part for part in [row["payee"], row["memo"]] if part).strip()
        category_name, matched_by, mapping_source = classify_from_db_rules(raw_text, rules)
        if category_name not in categories:
            category_name = None
        review_note = "" if mapping_source == "mapping" else "No mapping rule matched."
        parsed.append(
            ParsedUploadTransaction(
                posted_at=row["date"],
                amount=row["amount"],
                payee=row["payee"],
                memo=row["memo"],
                raw_text=raw_text,
                account_name=account_name,
                source_file=path.name,
                matched_by=matched_by,
                mapping_source=mapping_source,
                review_note=review_note,
                dedupe_signature=build_dedupe_signature(account_name, row["date"], row["amount"], row["payee"], row["memo"]),
                category_name=category_name,
            )
        )
    return parsed


def build_dedupe_signature(account_name: str, posted_at: datetime, amount: Decimal, payee: str, memo: str) -> str:
    payload = "|".join(
        [
            normalize(account_name),
            posted_at.strftime("%Y-%m-%d"),
            f"{amount:.2f}",
            normalize(payee),
            normalize(memo),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fingerprint(dedupe_signature: str, occurrence_index: int) -> str:
    return hashlib.sha256(f"{dedupe_signature}|{occurrence_index}".encode("utf-8")).hexdigest()


def existing_occurrence_count(
    db: Session,
    *,
    account_name: str,
    posted_at: datetime,
    amount: Decimal,
    payee: str,
    memo: str,
) -> int:
    rows = db.scalars(
        select(Transaction.id).where(
            Transaction.source_account_label == account_name,
            Transaction.posted_at == posted_at,
            Transaction.amount == amount,
            Transaction.payee == payee,
            Transaction.memo == memo,
        )
    ).all()
    return len(rows)


def transaction_to_dict(item: ParsedUploadTransaction) -> dict:
    raw = asdict(item)
    raw["posted_at"] = item.posted_at.isoformat()
    raw["amount"] = f"{item.amount:.2f}"
    return raw
