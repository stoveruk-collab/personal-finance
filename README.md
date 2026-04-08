# Personal Finance Ledger

`personal-finance` is a single-user finance app for importing manually downloaded bank and card exports, reviewing categorisation, and generating drill-down reporting from a clean ledger.

The project is designed for people who want:

- their own ledger and categorisation rules
- explicit import review before data is committed
- monthly and annual reporting without handing everything to a consumer finance product
- a deployable web app that can run locally or in the cloud

## What It Does

- Upload `.qif`, `.ofx`, and `.qfx` transaction files
- Detect account type from file content where possible
- De-duplicate transactions on import
- Apply editable mapping rules stored in the database
- Fall back to the OpenAI API when no mapping rule matches
- Let you override category suggestions before commit
- Show a combined ledger or account-specific ledger
- Generate monthly P&L views with expandable category detail
- Generate annual actual-vs-budget summaries
- Archive closed years while preserving aggregates and historical reports

## Architecture

The application has three main layers:

1. `FastAPI` server-rendered web app
2. `SQLAlchemy` data model that works with local SQLite and hosted PostgreSQL
3. Import/report services for parsing bank exports, categorising transactions, and building reports

Main components:

- Web app: `src/personal_finance/web/app.py`
- Data model: `src/personal_finance/web/models.py`
- Import parsing: `src/personal_finance/web/parsing.py`
- AI categorisation: `src/personal_finance/web/services/categorizer.py`
- Reporting: `src/personal_finance/web/reports.py`

## Key Flows

### Import Review

1. Upload one or more transaction exports.
2. Review the preview table before commit.
3. See which rows matched a saved mapping rule.
4. See which rows were suggested by AI.
5. Override any category.
6. Optionally save a corrected rule for future imports.
7. Commit the cleaned batch into the ledger.

### Reporting

- Monthly reports group by posting month and expand into underlying transactions.
- Annual reports compare actuals against the current monthly budget.
- Budgets are intentionally simple: one retroactive monthly budget per category.

### Ledger Browsing

- `/ledger` shows combined chronological detail
- `/accounts/<id>/ledger` filters to one account
- `/mappings` manages reusable categorisation rules
- `/budgets` manages monthly budget targets

## Authentication

The app uses Google OAuth for sign-in and supports a single allowed email address configured through environment variables.

## Local Development

```bash
cd personal-finance
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create an environment file from the example:

```bash
cp .env.example .env
```

Then run:

```bash
personal-finance serve-web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Environment

The important variables are:

- `APP_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `ALLOWED_GOOGLE_EMAIL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `DATABASE_URL`

The repository includes safe sample files in `config/` that you can replace with your own mappings and budgets.

## Deployment

The current hosted shape for this app is:

- `Google Cloud Run` for the web application
- `Google Cloud SQL for PostgreSQL` for the live database
- `Google Secret Manager` for app secrets
- `Google OAuth` for authentication
- `Cloud SQL automated backups` for nightly database protection

Primary deployment helper:

- `scripts/gcp-cloudrun-deploy.sh`

Deployment guide:

- `docs/gcp-cloudrun.md`
- `docs/runbook.md`

Container build:

- `Dockerfile`

Legacy AWS notes:

- `docs/aws-lightsail.md`

## Privacy

This public repository intentionally ships with:

- sample mapping rules
- sample budgets
- sample paths
- placeholder environment examples

No live credentials, exported transaction files, or private finance data are required to use the project.
