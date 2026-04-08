# Automation Strategy

## Recommendation

Build this as a local-first reporting project, not a full always-on app.

The expensive or brittle part is not report generation. It is authenticated transaction acquisition from bank/card portals. Report generation itself is cheap and can stay on your laptop until there is a clear reason to move it.

## Best Near-Term Architecture

1. Keep the source of truth in OneDrive month folders.
2. Use this repo to normalize exports, classify transactions, and produce monthly plus weekly summaries on demand.
3. Add automation only around getting files into the month folder.
4. If cloud is needed later, use AWS Lambda plus EventBridge or Step Functions, not a permanently running app server.

## HSBC

HSBC is the stronger candidate for real automation because UK banks participate in Open Banking and transaction access is designed around delegated account-information connections.

Practical options:

- use manual HSBC exports at first and standardize the filenames
- move to an Open Banking aggregator later if you want direct transaction pulls
- keep the normalized CSV output stable so the upstream acquisition method can change without rewriting reports

## Amex

Amex is usually the awkward one in family-finance automation. In practice, this often means one of:

- keep a manual export step
- use browser automation for download only
- use a third-party aggregation provider if it supports your exact Amex account and region

I would avoid building the whole system around Amex automation until we have confirmed a reliable acquisition path for your specific account.

## Browser Automation Path

If you want the most realistic next step, I would automate downloads with a local Playwright job that:

- opens Amex or HSBC in a real browser profile
- navigates to the export screen
- downloads the selected date range into the right month folder
- names files consistently for the reporting CLI

This avoids always-on infra and keeps secrets on your machine.

## Date-Range Strategy

The friction you called out is the exact date range. The cleanest way to reduce that is:

- monthly mode: first day of month through last day of month
- weekly checkpoint mode: first day of month through checkpoint date
- keep a small helper that prints or pre-fills the exact start and end dates for Amex and HSBC exports

Even before full browser automation, that removes the mental overhead.

## AWS View

AWS is optional here, not required.

Use AWS only when one of these becomes true:

- you want scheduled unattended pulls
- you want notifications after a monthly build
- you want a durable audit trail of imported source files

Until then, local CLI plus optional browser automation is the lowest-cost and lowest-risk setup.

