from __future__ import annotations

import csv
import re
from pathlib import Path

from personal_finance.config import DEFAULT_SETTINGS_PATH, PROJECT_ROOT, load_budget

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Account, BudgetSetting, Category, MappingRule


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def seed_defaults(db: Session) -> None:
    seed_accounts(db)
    seed_categories_and_mappings(db)
    seed_budget_settings(db)


def seed_accounts(db: Session) -> None:
    if db.scalar(select(Account.id).limit(1)) is not None:
        return

    import json

    settings = json.loads(DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8"))
    for account_cfg in settings["accounts"]:
        db.add(Account(name=account_cfg["name"], slug=slugify(account_cfg["name"])))
    db.commit()


def seed_categories_and_mappings(db: Session) -> None:
    if db.scalar(select(Category.id).limit(1)) is not None:
        return

    mapping_file = PROJECT_ROOT / "config" / "category_mapping.csv"
    with mapping_file.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    category_by_name: dict[str, Category] = {}
    for row in rows:
        category_name = row["Category"].strip()
        category = category_by_name.get(category_name)
        if category is None:
            category = Category(name=category_name, is_active=True)
            db.add(category)
            db.flush()
            category_by_name[category_name] = category
        db.add(
            MappingRule(
                priority=int(row["Priority"]),
                match_type=row["MatchType"].strip().lower(),
                pattern=row["Pattern"].strip(),
                category_id=category.id,
            )
        )
    db.commit()


def seed_budget_settings(db: Session) -> None:
    budget_by_category = load_budget(PROJECT_ROOT / "config" / "monthly_budget.csv")
    if not budget_by_category:
        return

    categories = db.scalars(select(Category)).all()
    existing = {
        budget.category.name: budget
        for budget in db.scalars(select(BudgetSetting).join(BudgetSetting.category)).all()
    }

    changed = False
    for category in categories:
        rule = budget_by_category.get(category.name)
        if rule is None:
            continue
        budget = existing.get(category.name)
        if budget is None:
            db.add(
                BudgetSetting(
                    category_id=category.id,
                    monthly_budget=rule.monthly_budget,
                )
            )
            changed = True
            continue
        if budget.monthly_budget != rule.monthly_budget:
            budget.monthly_budget = rule.monthly_budget
            changed = True

    if changed:
        db.commit()
