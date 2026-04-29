# GCP Cloud Run Deployment

This is the primary hosted deployment path for the app.

Production project:

- `personal-finance-wm-2026`

## Production Shape

- `Cloud Run` hosts the FastAPI web app
- `Cloud SQL for PostgreSQL` stores the live ledger
- `Secret Manager` holds app secrets
- `Google OAuth` handles sign-in

## Required GCP Services

Enable:

- `run.googleapis.com`
- `sqladmin.googleapis.com`
- `cloudbuild.googleapis.com`
- `artifactregistry.googleapis.com`
- `secretmanager.googleapis.com`
- `iam.googleapis.com`

## Required Secrets

Create these secrets in Secret Manager:

- `personal-finance-app-secret`
- `personal-finance-google-client-id`
- `personal-finance-google-client-secret`
- `personal-finance-openai-key`
- `personal-finance-db-password`

## Required Environment Values

The deployment script expects values like:

- `PROJECT_ID`
- `REGION`
- `SERVICE_NAME`
- `INSTANCE_NAME`
- `DB_NAME`
- `DB_USER`
- `ALLOWED_GOOGLE_EMAILS`
- `OWNER_LABEL`

The app itself uses:

- `APP_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `OPENAI_API_KEY`
- `DB_PASSWORD`

Those are passed through Secret Manager in production.

## Deploy

From the repo root:

```bash
./scripts/gcp-cloudrun-deploy.sh
```

The script:

1. builds the container from source
2. deploys it to Cloud Run
3. attaches the Cloud SQL instance
4. injects environment variables and secrets
5. labels the service for cost tracking

## GCP Authentication

Use this sequence before asking Codex to inspect or deploy Cloud Run resources:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project personal-finance-wm-2026
```

Verify the active account and project:

```bash
gcloud auth list --filter=status:ACTIVE
gcloud config get-value project
```

If you are running commands through Codex, use the repo wrapper instead of calling `gcloud` directly:

```bash
./scripts/gcloud-codex.sh auth list
./scripts/gcloud-codex.sh config get-value project
./scripts/gcloud-codex.sh run services describe personal-finance --region europe-west2
```

Why the wrapper exists:

- Codex runs in a sandbox where `~/.config/gcloud` may be readable but not writable
- `gcloud` often needs to write refreshed tokens during deploys
- `scripts/gcloud-codex.sh` copies your normal `gcloud` config into a writable temp directory and runs with `CLOUDSDK_CONFIG` pointed there

Important limitation:

- if the Codex session cannot reach Google APIs such as `oauth2.googleapis.com`, Codex cannot refresh credentials or deploy even if local auth already exists
- when tokens are expired, re-run `gcloud auth login` and `gcloud auth application-default login` in your normal local shell first, then retry through Codex

Recommended pre-deploy check:

```bash
./scripts/gcloud-codex.sh auth list --filter=status:ACTIVE
./scripts/gcloud-codex.sh config get-value project
./scripts/gcloud-codex.sh run services describe personal-finance --region europe-west2 >/dev/null
```

If the final command fails with an auth refresh or DNS/network error, fix local auth or network access before asking Codex to deploy.

## Cloud SQL

The application supports:

- local SQLite during development
- PostgreSQL in production

In Cloud Run, the app builds its database connection from:

- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `CLOUDSQL_CONNECTION_NAME`

## Nightly Backups

Cloud SQL automated backups are the primary at-rest backup mechanism for the deployed app.

Recommended baseline:

- automated backups: `enabled`
- start time: `03:00`
- retained backups: `7`
- region: same as the instance region

Current production expectation:

- instance: `personal-finance-db`
- region: `europe-west2`
- nightly backup window: `03:00`
- retained backups: `7`

Verify with:

```bash
gcloud sql instances describe personal-finance-db \
  --project "$PROJECT_ID" \
  --format='json(settings.backupConfiguration)'
```

If you need to change the schedule or retention:

```bash
gcloud sql instances patch personal-finance-db \
  --project "$PROJECT_ID" \
  --backup-start-time=03:00 \
  --retained-backups-count=7 \
  --quiet
```

## Google OAuth

Create a Google OAuth web client and add both local and hosted callbacks.

Typical values:

- local origin: `http://127.0.0.1:8000`
- local redirect: `http://127.0.0.1:8000/auth/google`
- production redirect: `https://<your-cloud-run-url>/auth/google`

Use `ALLOWED_GOOGLE_EMAILS` to restrict access to one or more approved users with a comma-separated allowlist.

## Notes

- `PUBLIC_BASE_URL` should match the external app URL if you use a custom domain or want explicit OAuth callback behavior.
- `max-instances=1` keeps the app simple for a single-user workflow and avoids multi-instance SQLite-style assumptions.
- Keep raw exports outside the repository and import them through the app.
