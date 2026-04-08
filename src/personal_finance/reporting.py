from __future__ import annotations

import calendar
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .config import BudgetRule, Settings, load_budget
from .ingest import Transaction, load_transactions


@dataclass(frozen=True)
class MonthContext:
    year: int
    month: int
    month_dir: Path
    title_month: str


def build_month_context(settings: Settings, year: int, month: int) -> MonthContext:
    title_month = datetime(year, month, 1).strftime("%B")
    month_dir = settings.finance_root / str(year) / f"{month:02d}"
    return MonthContext(year=year, month=month, month_dir=month_dir, title_month=title_month)


def format_gbp(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}GBP {abs(value):,.2f}"


def quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def budget_to_date(rule: BudgetRule, actual: Decimal, progress: Decimal) -> Decimal:
    if rule.checkpoint_mode == "full_month":
        return rule.monthly_budget if actual > 0 else Decimal("0")
    return rule.monthly_budget * progress


def init_month_folder(context: MonthContext) -> Path:
    context.month_dir.mkdir(parents=True, exist_ok=True)
    return context.month_dir


def monthly_transactions(settings: Settings, context: MonthContext) -> list[Transaction]:
    return load_transactions(
        month_dir=context.month_dir,
        mapping_file=settings.mapping_file,
        accounts=settings.accounts,
        year=context.year,
        month=context.month,
    )


def write_normalized_transactions(transactions: list[Transaction], output_file: Path) -> None:
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "account",
                "source_file",
                "payee",
                "memo",
                "amount",
                "category",
                "include_in_reports",
                "txn_direction",
                "matched_by",
                "mapping_source",
                "review_note",
            ]
        )
        for tx in transactions:
            writer.writerow(
                [
                    tx.date.strftime("%Y-%m-%d"),
                    tx.account,
                    tx.source_file,
                    tx.payee,
                    tx.memo,
                    f"{tx.amount:.2f}",
                    tx.category,
                    "yes" if tx.include_in_reports else "no",
                    tx.txn_direction,
                    tx.matched_by,
                    tx.mapping_source,
                    tx.review_note,
                ]
            )


def expense_totals(transactions: list[Transaction], through: date | None = None) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for tx in transactions:
        if through and tx.date.date() > through:
            continue
        if not tx.include_in_reports or tx.amount >= 0:
            continue
        totals[tx.category] += -tx.amount
    return totals


def review_items(transactions: list[Transaction], through: date | None = None) -> list[Transaction]:
    items = []
    for tx in transactions:
        if through and tx.date.date() > through:
            continue
        if tx.mapping_source != "mapping":
            items.append(tx)
    return items


def monthly_report(settings: Settings, year: int, month: int) -> tuple[Path, Path]:
    context = build_month_context(settings, year, month)
    init_month_folder(context)
    transactions = monthly_transactions(settings, context)
    budget = load_budget(settings.budget_file)

    normalized_file = context.month_dir / f"{context.title_month}_{year}_Normalized_Transactions.csv"
    summary_file = context.month_dir / f"{context.title_month}_{year}_Budget_Summary.md"
    write_normalized_transactions(transactions, normalized_file)

    spend = expense_totals(transactions)
    categories = sorted(set(budget) | set(spend))
    review = review_items(transactions)
    total_spend = sum(spend.values(), Decimal("0"))
    total_budget = sum((budget[category].monthly_budget for category in categories if category in budget), Decimal("0"))

    lines = [
        f"# {context.title_month} {year} Budget Summary",
        "",
        f"- Month folder: `{context.month_dir}`",
        f"- Transactions imported: {len(transactions)}",
        f"- Expense spend recorded: {format_gbp(quantize(total_spend))}",
        f"- Monthly budget tracked: {format_gbp(quantize(total_budget))}",
        f"- Variance: {format_gbp(quantize(total_spend - total_budget))}",
        "",
        "## Category Summary",
        "",
        "| Category | Actual | Budget | Variance |",
        "| --- | ---: | ---: | ---: |",
    ]

    for category in sorted(categories, key=lambda item: (-spend.get(item, Decimal("0")), item)):
        actual = quantize(spend.get(category, Decimal("0")))
        target = quantize(budget.get(category, BudgetRule(category=category, monthly_budget=Decimal("0"))).monthly_budget)
        variance = quantize(actual - target)
        lines.append(f"| {category} | {format_gbp(actual)} | {format_gbp(target)} | {format_gbp(variance)} |")

    lines.extend(
        [
            "",
            "## Review Queue",
            "",
        ]
    )

    if review:
        lines.append("| Date | Account | Payee | Amount | Proposed Category | Note |")
        lines.append("| --- | --- | --- | ---: | --- | --- |")
        for tx in review:
            lines.append(
                f"| {tx.date:%Y-%m-%d} | {tx.account} | {tx.payee or '(blank)'} | {format_gbp(quantize(-tx.amount if tx.amount < 0 else tx.amount))} | {tx.category} | {tx.review_note or tx.mapping_source} |"
            )
    else:
        lines.append("No review items. Everything matched the mapping file.")

    summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return normalized_file, summary_file


def weekly_checkpoint(settings: Settings, year: int, month: int, as_of: date) -> Path:
    context = build_month_context(settings, year, month)
    init_month_folder(context)
    transactions = monthly_transactions(settings, context)
    budget = load_budget(settings.budget_file)

    days_in_month = calendar.monthrange(year, month)[1]
    elapsed_days = Decimal(str(as_of.day))
    progress = elapsed_days / Decimal(str(days_in_month))
    spend = expense_totals(transactions, through=as_of)
    categories = sorted(set(budget) | set(spend))
    total_spend = sum(spend.values(), Decimal("0"))
    total_budget = sum((budget[category].monthly_budget for category in categories if category in budget), Decimal("0"))
    total_budget_to_date = sum(
        (
            budget_to_date(
                budget.get(category, BudgetRule(category=category, monthly_budget=Decimal("0"))),
                spend.get(category, Decimal("0")),
                progress,
            )
            for category in categories
        ),
        Decimal("0"),
    )
    checkpoint_file = context.month_dir / f"{as_of.isoformat()}_Weekly_Checkpoint.md"

    lines = [
        f"# Weekly Checkpoint for {as_of.isoformat()}",
        "",
        f"- Reporting month: {context.title_month} {year}",
        f"- Days elapsed: {as_of.day} of {days_in_month}",
        f"- Month progress: {progress * Decimal('100'):.1f}%",
        f"- Spend to date: {format_gbp(quantize(total_spend))}",
        f"- Budget to date: {format_gbp(quantize(total_budget_to_date))}",
        f"- Pace variance: {format_gbp(quantize(total_spend - total_budget_to_date))}",
        "",
        "## Pace by Category",
        "",
        "| Category | Spend To Date | Budget To Date | Forecast Month End | Pace Variance |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    for category in sorted(
        categories,
        key=lambda item: (
            -(
                spend.get(item, Decimal("0"))
                - budget_to_date(
                    budget.get(item, BudgetRule(category=item, monthly_budget=Decimal("0"))),
                    spend.get(item, Decimal("0")),
                    progress,
                )
            ),
            item,
        ),
    ):
        actual = quantize(spend.get(category, Decimal("0")))
        budget_rule = budget.get(category, BudgetRule(category=category, monthly_budget=Decimal("0")))
        budget_to_date_value = quantize(budget_to_date(budget_rule, spend.get(category, Decimal("0")), progress))
        forecast = quantize((actual / progress) if progress > 0 else Decimal("0"))
        variance = quantize(actual - budget_to_date_value)
        lines.append(
            f"| {category} | {format_gbp(actual)} | {format_gbp(budget_to_date_value)} | {format_gbp(forecast)} | {format_gbp(variance)} |"
        )

    review = review_items(transactions, through=as_of)
    lines.extend(["", "## Review Queue", ""])
    if review:
        for tx in review:
            lines.append(
                f"- {tx.date:%Y-%m-%d} | {tx.account} | {tx.payee or '(blank)'} | {format_gbp(quantize(-tx.amount if tx.amount < 0 else tx.amount))} | {tx.category} | {tx.review_note or tx.mapping_source}"
            )
    else:
        lines.append("- No review items through this checkpoint.")

    checkpoint_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checkpoint_file
