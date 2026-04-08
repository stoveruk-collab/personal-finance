from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"


@dataclass(frozen=True)
class AccountPattern:
    name: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    finance_root: Path
    mapping_file: Path
    budget_file: Path
    accounts: tuple[AccountPattern, ...]


@dataclass(frozen=True)
class BudgetRule:
    category: str
    monthly_budget: Decimal
    checkpoint_mode: str = "linear"


def _resolve_path(raw_path: str, *, env_var: str | None = None, config_dir_fallback: bool = False) -> Path:
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            return Path(override)

    path = Path(raw_path)
    if path.exists():
        return path

    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate

    if config_dir_fallback:
        candidate = PROJECT_ROOT / "config" / path.name
        if candidate.exists():
            return candidate

    return path


def load_settings(path: Path | None = None) -> Settings:
    settings_path = path or DEFAULT_SETTINGS_PATH
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    return Settings(
        finance_root=_resolve_path(raw["finance_root"], env_var="FINANCE_ROOT"),
        mapping_file=_resolve_path(raw["mapping_file"], env_var="MAPPING_FILE", config_dir_fallback=True),
        budget_file=_resolve_path(raw["budget_file"], env_var="BUDGET_FILE", config_dir_fallback=True),
        accounts=tuple(
            AccountPattern(name=item["name"], patterns=tuple(item["patterns"]))
            for item in raw["accounts"]
        ),
    )


def load_budget(path: Path) -> dict[str, BudgetRule]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["category"].strip(): BudgetRule(
                category=row["category"].strip(),
                monthly_budget=Decimal(row["monthly_budget_gbp"].strip()),
                checkpoint_mode=(row.get("checkpoint_mode") or "linear").strip(),
            )
            for row in csv.DictReader(handle)
        }
