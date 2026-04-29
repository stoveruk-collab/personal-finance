from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.web.db import Base
from personal_finance.web.models import Account, BudgetSetting, Category, ImportBatch, Transaction
from personal_finance.web.reports import annual_report_data, monthly_report_data


def add_transaction(
    db: Session,
    *,
    batch: ImportBatch,
    account: Account,
    category: Category,
    fingerprint: str,
    posted_at: datetime,
    amount: str,
    payee: str,
) -> None:
    db.add(
        Transaction(
            fingerprint=fingerprint,
            year=posted_at.year,
            posted_at=posted_at,
            amount=Decimal(amount),
            payee=payee,
            memo="",
            raw_text=payee,
            source_file="test.ofx",
            source_account_label=account.name,
            matched_by="",
            mapping_source="mapping",
            review_note="",
            ai_guess_reason="",
            ai_guess_model="",
            account_id=account.id,
            category_id=category.id,
            import_batch_id=batch.id,
        )
    )


def test_monthly_report_treats_business_expense_as_receivable():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = Session(bind=engine, future=True)

    account = Account(name="Checking", slug="checking")
    groceries = Category(name="Groceries & Supplies")
    business = Category(name="Business Expense")
    db.add_all([account, groceries, business])
    db.commit()

    db.add(BudgetSetting(category_id=groceries.id, monthly_budget=Decimal("500.00")))
    db.add(BudgetSetting(category_id=business.id, monthly_budget=Decimal("0.00")))
    batch = ImportBatch(uploaded_files="test.ofx", notes="")
    db.add(batch)
    db.commit()

    add_transaction(
        db,
        batch=batch,
        account=account,
        category=groceries,
        fingerprint="groceries-1",
        posted_at=datetime(2026, 4, 3),
        amount="-50.00",
        payee="Tesco",
    )
    add_transaction(
        db,
        batch=batch,
        account=account,
        category=business,
        fingerprint="business-1",
        posted_at=datetime(2026, 4, 4),
        amount="-100.00",
        payee="Work trip hotel",
    )
    add_transaction(
        db,
        batch=batch,
        account=account,
        category=business,
        fingerprint="business-2",
        posted_at=datetime(2026, 4, 10),
        amount="30.00",
        payee="Employer reimbursement",
    )
    db.commit()

    report = monthly_report_data(db, 2026, 4)

    assert report["total_expenses"] == Decimal("50.00")
    assert report["total_budget"] == Decimal("500.00")
    assert [section["category"] for section in report["expense_sections"]] == ["Groceries & Supplies"]
    assert report["business_expense"]["charges"] == Decimal("100.00")
    assert report["business_expense"]["reimbursements"] == Decimal("30.00")
    assert report["business_expense"]["net_receivable"] == Decimal("70.00")
    assert len(report["business_expense"]["transactions"]) == 2

    db.close()


def test_annual_report_tracks_business_expense_separately_from_budget():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = Session(bind=engine, future=True)

    account = Account(name="Checking", slug="checking")
    groceries = Category(name="Groceries & Supplies")
    business = Category(name="Business Expense")
    db.add_all([account, groceries, business])
    db.commit()

    db.add(BudgetSetting(category_id=groceries.id, monthly_budget=Decimal("500.00")))
    db.add(BudgetSetting(category_id=business.id, monthly_budget=Decimal("0.00")))
    batch = ImportBatch(uploaded_files="test.ofx", notes="")
    db.add(batch)
    db.commit()

    add_transaction(
        db,
        batch=batch,
        account=account,
        category=groceries,
        fingerprint="groceries-1",
        posted_at=datetime(2026, 4, 3),
        amount="-50.00",
        payee="Tesco",
    )
    add_transaction(
        db,
        batch=batch,
        account=account,
        category=business,
        fingerprint="business-1",
        posted_at=datetime(2026, 4, 4),
        amount="-100.00",
        payee="Work trip hotel",
    )
    add_transaction(
        db,
        batch=batch,
        account=account,
        category=business,
        fingerprint="business-2",
        posted_at=datetime(2026, 4, 10),
        amount="30.00",
        payee="Employer reimbursement",
    )
    db.commit()

    report = annual_report_data(db, 2026)

    assert [row["category"] for row in report["category_rows"]] == ["Groceries & Supplies"]
    assert report["total_expenses"] == Decimal("50.00")
    assert report["total_budget"] == Decimal("500.00")
    assert report["business_expense"]["charges"] == Decimal("100.00")
    assert report["business_expense"]["reimbursements"] == Decimal("30.00")
    assert report["business_expense"]["net_receivable"] == Decimal("70.00")
    assert report["months"][0]["business_expense_net_receivable"] == Decimal("70.00")

    db.close()
