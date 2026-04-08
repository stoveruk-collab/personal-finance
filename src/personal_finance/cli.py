from __future__ import annotations

import argparse
from datetime import datetime

from .config import load_settings
from .reporting import build_month_context, init_month_folder, monthly_report, weekly_checkpoint
from .web.app import run as run_web_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal finance reporting tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-month", help="Create the target month folder if it does not exist")
    init_parser.add_argument("--year", type=int, required=True)
    init_parser.add_argument("--month", type=int, required=True)

    month_parser = subparsers.add_parser("monthly-report", help="Build normalized transactions and a monthly markdown summary")
    month_parser.add_argument("--year", type=int, required=True)
    month_parser.add_argument("--month", type=int, required=True)

    checkpoint_parser = subparsers.add_parser("weekly-checkpoint", help="Build an in-month budget checkpoint")
    checkpoint_parser.add_argument("--year", type=int, required=True)
    checkpoint_parser.add_argument("--month", type=int, required=True)
    checkpoint_parser.add_argument("--as-of", type=lambda item: datetime.strptime(item, "%Y-%m-%d").date(), required=True)

    subparsers.add_parser("serve-web", help="Run the finance web application locally")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()

    if args.command == "init-month":
        context = build_month_context(settings, args.year, args.month)
        path = init_month_folder(context)
        print(path)
        return

    if args.command == "monthly-report":
        normalized_file, summary_file = monthly_report(settings, args.year, args.month)
        print(normalized_file)
        print(summary_file)
        return

    if args.command == "weekly-checkpoint":
        checkpoint_path = weekly_checkpoint(settings, args.year, args.month, args.as_of)
        print(checkpoint_path)
        return

    if args.command == "serve-web":
        run_web_app()
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
