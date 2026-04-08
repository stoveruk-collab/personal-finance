from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    mapping_rules: Mapped[list["MappingRule"]] = relationship(back_populates="category")
    budget_setting: Mapped[Optional["BudgetSetting"]] = relationship(back_populates="category")


class MappingRule(Base):
    __tablename__ = "mapping_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    category: Mapped[Category] = relationship(back_populates="mapping_rules")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_files: Mapped[str] = mapped_column(Text, nullable=False)
    imported_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="import_batch")


class ImportPreview(Base):
    __tablename__ = "import_previews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_transactions_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payee: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    memo: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_account_label: Mapped[str] = mapped_column(String(255), nullable=False)
    matched_by: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_guess_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_guess_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"))

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Optional[Category]] = relationship(back_populates="transactions")
    import_batch: Mapped[Optional[ImportBatch]] = relationship(back_populates="transactions")


class YearClose(Base):
    __tablename__ = "year_closes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    aggregates: Mapped[list["YearCategoryAggregate"]] = relationship(back_populates="year_close")
    reports: Mapped[list["HistoricalReport"]] = relationship(back_populates="year_close")


class YearCategoryAggregate(Base):
    __tablename__ = "year_category_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_close_id: Mapped[int] = mapped_column(ForeignKey("year_closes.id"), nullable=False)
    category_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)

    year_close: Mapped[YearClose] = relationship(back_populates="aggregates")


class HistoricalReport(Base):
    __tablename__ = "historical_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year_close_id: Mapped[int] = mapped_column(ForeignKey("year_closes.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    report_name: Mapped[str] = mapped_column(String(255), nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)

    year_close: Mapped[YearClose] = relationship(back_populates="reports")


class BudgetSetting(Base):
    __tablename__ = "budget_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), unique=True, nullable=False)
    monthly_budget: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    category: Mapped[Category] = relationship(back_populates="budget_setting")
