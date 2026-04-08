# Reporting Workflow

## Recommended Source Layout

Keep raw exports outside the repository and import them through the web app or CLI.

Example structure:

- `finance-data/YYYY/MM`

That directory can contain:

- raw `.qif`, `.ofx`, or `.qfx` exports
- notes about a monthly close
- generated summaries or reconciliations

## Suggested Process

1. Download bank and card exports for the period you want to review.
2. Import them into the app.
3. Review any unmapped or AI-suggested categorizations.
4. Save new mapping rules where useful.
5. Re-open the monthly or annual report after commit.

## Weekly Checkpoints

Weekly checkpoints are most useful for:

- actual spend to date
- actual vs monthly budget
- identifying categories that need a mapping cleanup

## Month-End

For a month-end close:

1. Import final exports for the month.
2. Review transfers and uncategorised rows.
3. Confirm the monthly P&L.
4. Archive year-end data only when you are ready to close the year.
