from __future__ import annotations

import argparse
from datetime import datetime

from .config import load_settings
from .downloader import build_download_plan, run_download
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

    download_parser = subparsers.add_parser("download-transactions", help="Download statement transactions for a month or partial month")
    download_parser.add_argument("--provider", required=True, choices=["amex", "hsbc-current", "hsbc-credit"])
    download_parser.add_argument("--period", help="Month name like April or YYYY-MM")
    download_parser.add_argument("--year", type=int)
    download_parser.add_argument("--month", type=int)
    download_parser.add_argument("--headed", action="store_true")
    download_parser.add_argument("--interactive-login", action="store_true")
    download_parser.add_argument("--keep-open", action="store_true")
    download_parser.add_argument("--plan-only", action="store_true")

    codegen_parser = subparsers.add_parser("codegen-command", help="Print the Playwright codegen command for a provider")
    codegen_parser.add_argument("--provider", required=True, choices=["amex", "hsbc-current", "hsbc-credit"])

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

    if args.command == "download-transactions":
        plan = build_download_plan(
            provider=args.provider,
            period=args.period,
            month=args.month,
            year=args.year,
        )
        if args.plan_only:
            print(f"provider={plan.provider}")
            print(f"from={plan.date_range.start.isoformat()}")
            print(f"to={plan.date_range.end.isoformat()}")
            print(f"out_dir={plan.output_dir}")
            return

        run_download(
            provider=args.provider,
            period=args.period,
            month=args.month,
            year=args.year,
            headed=args.headed,
            interactive_login=args.interactive_login,
            keep_open=args.keep_open,
        )
        return

    if args.command == "codegen-command":
        if args.provider == "amex":
            print("npm run codegen:amex")
            return
        print("npm run codegen:hsbc")
        return

    if args.command == "serve-web":
        run_web_app()
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
