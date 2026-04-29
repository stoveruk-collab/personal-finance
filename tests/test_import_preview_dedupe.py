from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.web.db import Base
from personal_finance.web.models import Account, Category, ImportBatch, Transaction
from personal_finance.web.parsing import build_dedupe_signature, build_fingerprint, dedupe_sort_key, existing_occurrence_count


class ImportPreviewDeduplicationTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        self.db = Session(bind=engine, future=True)

        self.account = Account(name="Checking", slug="checking")
        self.category = Category(name="Groceries")
        self.batch = ImportBatch(uploaded_files="existing.qfx", notes="")
        self.db.add_all([self.account, self.category, self.batch])
        self.db.commit()

        self.posted_at = datetime(2026, 4, 1, 0, 0)
        self.amount = Decimal("-12.34")
        self.payee = "Corner Shop"
        self.memo = ""
        self.account_name = "Checking"
        self.signature = build_dedupe_signature(
            self.account_name,
            self.posted_at,
            self.amount,
            self.payee,
            self.memo,
        )

    def tearDown(self):
        self.db.close()

    def test_existing_occurrence_count_counts_matching_ledger_rows(self):
        self.db.add(
            Transaction(
                fingerprint=build_fingerprint(self.signature, 1),
                year=self.posted_at.year,
                posted_at=self.posted_at,
                amount=self.amount,
                payee=self.payee,
                memo=self.memo,
                raw_text=self.payee,
                source_file="existing.qfx",
                source_account_label=self.account_name,
                matched_by="",
                mapping_source="mapping",
                review_note="",
                ai_guess_reason="",
                ai_guess_model="",
                account_id=self.account.id,
                category_id=self.category.id,
                import_batch_id=self.batch.id,
            )
        )
        self.db.commit()

        existing_count = existing_occurrence_count(
            self.db,
            account_name=self.account_name,
            posted_at=self.posted_at,
            amount=self.amount,
            payee=self.payee,
            memo=self.memo,
        )

        self.assertEqual(existing_count, 1)

    def test_existing_occurrence_count_does_not_treat_upload_only_duplicates_as_existing(self):
        existing_count = existing_occurrence_count(
            self.db,
            account_name=self.account_name,
            posted_at=self.posted_at,
            amount=self.amount,
            payee=self.payee,
            memo=self.memo,
        )

        self.assertEqual(existing_count, 0)

    def test_existing_occurrence_count_normalizes_account_payee_and_memo(self):
        self.db.add(
            Transaction(
                fingerprint=build_fingerprint(self.signature, 1),
                year=self.posted_at.year,
                posted_at=self.posted_at,
                amount=self.amount,
                payee="  corner   shop ",
                memo=" weekly groceries ",
                raw_text=self.payee,
                source_file="existing.qfx",
                source_account_label=" checking ",
                matched_by="",
                mapping_source="mapping",
                review_note="",
                ai_guess_reason="",
                ai_guess_model="",
                account_id=self.account.id,
                category_id=self.category.id,
                import_batch_id=self.batch.id,
            )
        )
        self.db.commit()

        existing_count = existing_occurrence_count(
            self.db,
            account_name="Checking",
            posted_at=self.posted_at,
            amount=self.amount,
            payee="Corner Shop",
            memo="Weekly Groceries",
        )

        self.assertEqual(existing_count, 1)

    def test_existing_occurrence_count_ignores_account_mismatches(self):
        other_account = Account(name="Credit Account", slug="credit-account")
        self.db.add(other_account)
        self.db.commit()

        self.db.add(
            Transaction(
                fingerprint=build_fingerprint(self.signature, 1),
                year=self.posted_at.year,
                posted_at=self.posted_at,
                amount=self.amount,
                payee=self.payee,
                memo=self.memo,
                raw_text=self.payee,
                source_file="existing.qfx",
                source_account_label="Old Guessed Account",
                matched_by="",
                mapping_source="mapping",
                review_note="",
                ai_guess_reason="",
                ai_guess_model="",
                account_id=other_account.id,
                category_id=self.category.id,
                import_batch_id=self.batch.id,
            )
        )
        self.db.commit()

        existing_count = existing_occurrence_count(
            self.db,
            account_name=self.account_name,
            posted_at=self.posted_at,
            amount=self.amount,
            payee=self.payee,
            memo=self.memo,
        )

        self.assertEqual(existing_count, 1)

    def test_existing_occurrence_count_ignores_memo_when_payee_matches(self):
        self.db.add(
            Transaction(
                fingerprint=build_fingerprint(self.signature, 1),
                year=self.posted_at.year,
                posted_at=self.posted_at,
                amount=self.amount,
                payee="BRITISH GAS",
                memo="",
                raw_text="BRITISH GAS",
                source_file="existing.qfx",
                source_account_label=self.account_name,
                matched_by="",
                mapping_source="mapping",
                review_note="",
                ai_guess_reason="",
                ai_guess_model="",
                account_id=self.account.id,
                category_id=self.category.id,
                import_batch_id=self.batch.id,
            )
        )
        self.db.commit()

        existing_count = existing_occurrence_count(
            self.db,
            account_name=self.account_name,
            posted_at=self.posted_at,
            amount=self.amount,
            payee="BRITISH GAS",
            memo="DD",
        )

        self.assertEqual(existing_count, 1)

    def test_dedupe_sort_key_orders_oldest_to_newest(self):
        older = dedupe_sort_key(
            posted_at=datetime(2026, 4, 1, 0, 0),
            account_name="Checking",
            payee="B Shop",
            amount=Decimal("-2.00"),
        )
        newer = dedupe_sort_key(
            posted_at=datetime(2026, 4, 2, 0, 0),
            account_name="Checking",
            payee="A Shop",
            amount=Decimal("-1.00"),
        )

        self.assertLess(older, newer)


if __name__ == "__main__":
    unittest.main()
