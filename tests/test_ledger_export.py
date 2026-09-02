import csv
import io
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.web.app import export_ledger
from personal_finance.web.db import Base
from personal_finance.web.models import Account, Category, Transaction, User


class LedgerExportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        self.user = User(email="test@example.com", name="Test User", google_sub="test-user")
        self.current_account = Account(name="Current Account", slug="current")
        self.savings_account = Account(name="Savings", slug="savings")
        self.category = Category(name="Groceries", is_active=True)
        self.db.add_all(
            [self.user, self.current_account, self.savings_account, self.category]
        )
        self.db.flush()

        self.db.add_all(
            [
                self.transaction(
                    "target",
                    datetime(2026, 1, 15),
                    self.current_account,
                    Decimal("-12.34"),
                    payee="Market, Hall",
                    memo='Weekly "shop"',
                    raw_text="receipt needle",
                    category=self.category,
                ),
                self.transaction(
                    "wrong-search",
                    datetime(2026, 1, 16),
                    self.current_account,
                    Decimal("-8.00"),
                    payee="Corner shop",
                ),
                self.transaction(
                    "wrong-account",
                    datetime(2026, 1, 17),
                    self.savings_account,
                    Decimal("10.00"),
                    raw_text="needle",
                ),
                self.transaction(
                    "wrong-month",
                    datetime(2026, 2, 1),
                    self.current_account,
                    Decimal("-4.00"),
                    raw_text="needle",
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def transaction(
        fingerprint,
        posted_at,
        account,
        amount,
        payee="",
        memo="",
        raw_text="",
        category=None,
    ):
        return Transaction(
            fingerprint=fingerprint,
            year=posted_at.year,
            posted_at=posted_at,
            amount=amount,
            payee=payee,
            memo=memo,
            raw_text=raw_text,
            source_file="test.qif",
            source_account_label=account.name,
            account=account,
            category=category,
        )

    def test_csv_export_applies_account_month_and_search_filters(self):
        response = export_ledger(
            db=self.db,
            user=self.user,
            account_id=str(self.current_account.id),
            month="2026-01",
            search="needle",
        )

        rows = list(csv.reader(io.StringIO(response.body.decode("utf-8"))))

        self.assertEqual(response.media_type, "text/csv")
        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="ledger-transactions-2026-01.csv"',
        )
        self.assertEqual(
            rows[0], ["Date", "Account", "Payee", "Memo", "Category", "Amount"]
        )
        self.assertEqual(
            rows[1],
            [
                "2026-01-15",
                "Current Account",
                "Market, Hall",
                'Weekly "shop"',
                "Groceries",
                "-12.34",
            ],
        )
        self.assertEqual(len(rows), 2)

    def test_csv_export_labels_transactions_without_a_category(self):
        response = export_ledger(
            db=self.db,
            user=self.user,
            account_id=str(self.current_account.id),
            month="2026-01",
            search="Corner shop",
        )

        rows = list(csv.reader(io.StringIO(response.body.decode("utf-8"))))

        self.assertEqual(rows[1][4], "Uncategorised")


if __name__ == "__main__":
    unittest.main()
