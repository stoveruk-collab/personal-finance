# Downloader Setup

## What It Does

The downloader is a local Playwright runner for statement exports.

It already handles:

- turning `April` into `2026-04-01` through `2026-04-07` when run on 7 April 2026
- creating the right `YYYY/MM` output folder
- saving downloads with stable names
- preserving a local authenticated browser session after interactive login

## What Still Needs One-Time Setup

Because bank and card portal markup changes over time, the final selectors should be captured from your own sessions.

### Install Dependencies

```bash
cd personal-finance
npm install
npm run install:browsers
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Capture Selectors

Use Playwright codegen to inspect the portal and capture stable selectors:

```bash
npx playwright codegen https://global.americanexpress.com/
```

and:

```bash
npx playwright codegen https://www.hsbc.co.uk/
```

Then populate these fields in `config/downloaders.json` for each provider:

- `post_login_ready`
- `date_from_input`
- `date_to_input`
- `download_trigger`

Or use the helper script:

```bash
node scripts/set-provider-selectors.mjs \
  --provider amex \
  --post-login-ready "text=Statements" \
  --date-from-input "input[name='fromDate']" \
  --date-to-input "input[name='toDate']" \
  --download-trigger "button:has-text('Download')"
```

## Example Usage

Plan only:

```bash
personal-finance download-transactions --provider hsbc-current --period April --year 2026 --plan-only
```

Interactive run:

```bash
personal-finance download-transactions --provider hsbc-current --period April --year 2026 --headed --interactive-login
```

## Expected Behaviour for April Right Now

If today is 7 April 2026 and you request `April`, the downloader plans:

- start date: `2026-04-01`
- end date: `2026-04-07`

That is true whether you specify `--period April --year 2026` or `--year 2026 --month 4`.
