from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import extract, select
from sqlalchemy.orm import Session, joinedload

from .models import BudgetSetting, HistoricalReport, Transaction, YearCategoryAggregate, YearClose

BUSINESS_EXPENSE_CATEGORY = "Business Expense"


def format_gbp(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}£{abs(value):,.2f}"


def month_name(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B")


def month_options(db: Session) -> list[dict[str, int | str]]:
    values = (
        db.execute(
            select(Transaction.year, extract("month", Transaction.posted_at).label("month"))
            .distinct()
            .order_by(Transaction.year.desc(), extract("month", Transaction.posted_at).desc())
        )
        .all()
    )
    return [{"year": int(year), "month": int(month), "label": f"{month_name(int(year), int(month))} {int(year)}"} for year, month in values]


def available_years(db: Session) -> list[int]:
    return sorted(set(db.scalars(select(Transaction.year)).all()), reverse=True)


def budget_settings(db: Session) -> list[BudgetSetting]:
    return db.scalars(
        select(BudgetSetting)
        .options(joinedload(BudgetSetting.category))
        .join(BudgetSetting.category)
        .order_by(BudgetSetting.category_id)
    ).all()


def monthly_report_data(db: Session, year: int, month: int) -> dict:
    transactions = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .where(Transaction.year == year)
        .where(extract("month", Transaction.posted_at) == month)
        .order_by(Transaction.posted_at, Transaction.id)
    ).all()

    budgets = {
        budget.category.name: Decimal(str(budget.monthly_budget))
        for budget in budget_settings(db)
        if budget.category is not None
    }
    income_totals: dict[str, Decimal] = defaultdict(Decimal)
    expense_totals: dict[str, Decimal] = defaultdict(Decimal)
    detail_rows: dict[str, list[Transaction]] = defaultdict(list)
    transfers_excluded = Decimal("0")
    business_expense_charges = Decimal("0")
    business_expense_reimbursements = Decimal("0")

    for tx in transactions:
        category_name = tx.category.name if tx.category else "Uncategorised"
        detail_rows[category_name].append(tx)
        amount = Decimal(str(tx.amount))
        if category_name == "Transfer":
            transfers_excluded += abs(amount)
            continue
        if category_name == BUSINESS_EXPENSE_CATEGORY:
            if amount < 0:
                business_expense_charges += -amount
            elif amount > 0:
                business_expense_reimbursements += amount
            continue
        if amount > 0:
            income_totals[category_name] += amount
        else:
            expense_totals[category_name] += -amount

    total_income = sum(income_totals.values(), Decimal("0"))
    total_expenses = sum(expense_totals.values(), Decimal("0"))
    net_surplus = total_income - total_expenses
    total_budget = sum((budgets.get(category, Decimal("0")) for category in expense_totals), Decimal("0"))

    income_order = ["Salary", "Miscellaneous"]
    ordered_income_categories = [name for name in income_order if name in income_totals] + [
        name for name in sorted(income_totals) if name not in income_order
    ]

    expense_sections = [
        {
            "category": category,
            "amount": amount,
            "budget": budgets.get(category, Decimal("0")),
            "variance": budgets.get(category, Decimal("0")) - amount,
            "transactions": [tx for tx in detail_rows[category] if Decimal(str(tx.amount)) < 0],
        }
        for category, amount in sorted(expense_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    income_sections = [
        {
            "category": "Miscellaneous (RSU sale proceeds)" if category == "Miscellaneous" else category,
            "raw_category": category,
            "amount": income_totals[category],
            "transactions": [tx for tx in detail_rows[category] if Decimal(str(tx.amount)) > 0],
        }
        for category in ordered_income_categories
    ]
    excluded_transfers = [tx for tx in transactions if (tx.category.name if tx.category else "Uncategorised") == "Transfer"]
    review_rows = [tx for tx in transactions if tx.review_note or tx.ai_guess_reason]
    business_expense_net = business_expense_charges - business_expense_reimbursements
    business_expense_transactions = detail_rows[BUSINESS_EXPENSE_CATEGORY]

    return {
        "title_month": month_name(year, month),
        "year": year,
        "month": month,
        "transactions": transactions,
        "income_sections": income_sections,
        "expense_sections": expense_sections,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_surplus": net_surplus,
        "total_budget": total_budget,
        "budget_variance": total_budget - total_expenses,
        "transfers_excluded": transfers_excluded,
        "excluded_transfers": excluded_transfers,
        "review_rows": review_rows,
        "business_expense": {
            "category": BUSINESS_EXPENSE_CATEGORY,
            "charges": business_expense_charges,
            "reimbursements": business_expense_reimbursements,
            "net_receivable": business_expense_net,
            "transactions": business_expense_transactions,
        },
    }


def annual_report_data(db: Session, year: int) -> dict:
    budgets = budget_settings(db)
    budget_by_category = {
        budget.category.name: Decimal(str(budget.monthly_budget))
        for budget in budgets
        if budget.category is not None
    }

    transactions = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.category))
        .where(Transaction.year == year)
        .order_by(Transaction.posted_at, Transaction.id)
    ).all()

    category_month_actuals: dict[str, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    month_expense_totals: dict[int, Decimal] = defaultdict(Decimal)
    month_income_totals: dict[int, Decimal] = defaultdict(Decimal)
    month_business_expense_charges: dict[int, Decimal] = defaultdict(Decimal)
    month_business_expense_reimbursements: dict[int, Decimal] = defaultdict(Decimal)

    for tx in transactions:
        category_name = tx.category.name if tx.category else "Uncategorised"
        if category_name == "Transfer":
            continue
        amount = Decimal(str(tx.amount))
        month = tx.posted_at.month
        if category_name == BUSINESS_EXPENSE_CATEGORY:
            if amount < 0:
                month_business_expense_charges[month] += -amount
            elif amount > 0:
                month_business_expense_reimbursements[month] += amount
            continue
        if amount > 0:
            month_income_totals[month] += amount
        else:
            expense = -amount
            month_expense_totals[month] += expense
            category_month_actuals[category_name][month] += expense

    months_present = sorted({month for month in {*month_income_totals.keys(), *month_expense_totals.keys()} if month_income_totals.get(month, Decimal("0")) or month_expense_totals.get(month, Decimal("0"))})

    annual_rows: list[dict] = []
    category_names = sorted((set(budget_by_category) | set(category_month_actuals)) - {BUSINESS_EXPENSE_CATEGORY})
    for category_name in category_names:
        monthly_budget = budget_by_category.get(category_name, Decimal("0"))
        month_cells = []
        total_actual = Decimal("0")
        for month in months_present:
            actual = category_month_actuals[category_name].get(month, Decimal("0"))
            total_actual += actual
            month_cells.append(
                {
                    "month": month,
                    "actual": actual,
                    "budget": monthly_budget,
                    "variance": monthly_budget - actual,
                }
            )
        annual_budget = monthly_budget * Decimal(len(months_present))
        annual_rows.append(
            {
                "category": category_name,
                "monthly_budget": monthly_budget,
                "months": month_cells,
                "total_actual": total_actual,
                "annual_budget": annual_budget,
                "annual_variance": annual_budget - total_actual,
            }
        )

    annual_rows.sort(key=lambda row: (-row["total_actual"], row["category"]))
    month_summaries = []
    for month in months_present:
        budget_total = sum((row["months"][index]["budget"] for row in annual_rows for index, cell in enumerate(row["months"]) if cell["month"] == month), Decimal("0"))
        expenses = month_expense_totals.get(month, Decimal("0"))
        income = month_income_totals.get(month, Decimal("0"))
        business_expense_charges = month_business_expense_charges.get(month, Decimal("0"))
        business_expense_reimbursements = month_business_expense_reimbursements.get(month, Decimal("0"))
        month_summaries.append(
            {
                "month": month,
                "label": calendar.month_abbr[month],
                "income": income,
                "expenses": expenses,
                "budget": budget_total,
                "variance": budget_total - expenses,
                "net": income - expenses,
                "business_expense_charges": business_expense_charges,
                "business_expense_reimbursements": business_expense_reimbursements,
                "business_expense_net_receivable": business_expense_charges - business_expense_reimbursements,
            }
        )

    total_income = sum((row["income"] for row in month_summaries), Decimal("0"))
    total_expenses = sum((row["expenses"] for row in month_summaries), Decimal("0"))
    total_budget = sum((row["budget"] for row in month_summaries), Decimal("0"))
    total_business_expense_charges = sum((row["business_expense_charges"] for row in month_summaries), Decimal("0"))
    total_business_expense_reimbursements = sum((row["business_expense_reimbursements"] for row in month_summaries), Decimal("0"))

    return {
        "year": year,
        "months": month_summaries,
        "category_rows": annual_rows,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_budget": total_budget,
        "budget_variance": total_budget - total_expenses,
        "net_surplus": total_income - total_expenses,
        "business_expense": {
            "category": BUSINESS_EXPENSE_CATEGORY,
            "charges": total_business_expense_charges,
            "reimbursements": total_business_expense_reimbursements,
            "net_receivable": total_business_expense_charges - total_business_expense_reimbursements,
        },
    }


def close_year(db: Session, year: int, render_html) -> YearClose:
    existing = db.scalar(select(YearClose).where(YearClose.year == year))
    if existing is not None:
        raise ValueError(f"Year {year} has already been closed.")

    year_close = YearClose(year=year)
    db.add(year_close)
    db.flush()

    aggregates: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)

    for month in range(1, 13):
        report = monthly_report_data(db, year, month)
        if not report["transactions"]:
            continue
        html = render_html(report)
        db.add(
            HistoricalReport(
                year_close_id=year_close.id,
                year=year,
                month=month,
                report_name=f"{month_name(year, month)} {year} P&L",
                html=html,
            )
        )
        for section in report["expense_sections"]:
            aggregates[section["category"]] += section["amount"]
            counts[section["category"]] += len(section["transactions"])

    for category_name, amount in sorted(aggregates.items()):
        db.add(
            YearCategoryAggregate(
                year_close_id=year_close.id,
                category_name=category_name,
                amount=amount,
                transaction_count=counts[category_name],
            )
        )

    transactions = db.scalars(select(Transaction).where(Transaction.year == year)).all()
    for transaction in transactions:
        db.delete(transaction)

    db.commit()
    db.refresh(year_close)
    return year_close
