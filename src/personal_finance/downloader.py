from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import PROJECT_ROOT, load_settings
from .date_ranges import DateRange, resolve_month_date_range, resolve_period


DOWNLOADERS_CONFIG_PATH = PROJECT_ROOT / "config" / "downloaders.json"
NODE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "download-transactions.mjs"


@dataclass(frozen=True)
class DownloadPlan:
    provider: str
    year: int
    month: int
    date_range: DateRange
    output_dir: Path


def build_download_plan(
    provider: str,
    period: str | None = None,
    month: int | None = None,
    year: int | None = None,
    today: date | None = None,
) -> DownloadPlan:
    settings = load_settings()

    if period:
        resolved_year, resolved_month, date_range = resolve_period(period=period, year=year, today=today)
    elif month and year:
        date_range = resolve_month_date_range(month=month, year=year, today=today)
        resolved_year = year
        resolved_month = month
    else:
        raise ValueError("Provide either --period or both --year and --month.")

    output_dir = settings.finance_root / str(resolved_year) / f"{resolved_month:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)

    return DownloadPlan(
        provider=provider,
        year=resolved_year,
        month=resolved_month,
        date_range=date_range,
        output_dir=output_dir,
    )


def provider_exists(provider: str) -> bool:
    config = json.loads(DOWNLOADERS_CONFIG_PATH.read_text(encoding="utf-8"))
    return provider in config.get("providers", {})


def run_download(
    provider: str,
    period: str | None = None,
    month: int | None = None,
    year: int | None = None,
    headed: bool = True,
    interactive_login: bool = False,
    keep_open: bool = False,
) -> DownloadPlan:
    if not provider_exists(provider):
        raise ValueError(f"Unknown provider: {provider}")

    plan = build_download_plan(provider=provider, period=period, month=month, year=year)
    command = [
        "node",
        str(NODE_SCRIPT_PATH),
        "--provider",
        provider,
        "--from",
        plan.date_range.start.isoformat(),
        "--to",
        plan.date_range.end.isoformat(),
        "--out-dir",
        str(plan.output_dir),
    ]
    if headed:
        command.append("--headed")
    if interactive_login:
        command.append("--interactive-login")
    if keep_open:
        command.append("--keep-open")

    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return plan

