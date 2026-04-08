# GCP Cloud Run Deployment

This is the primary hosted deployment path for the app.

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
- `ALLOWED_GOOGLE_EMAIL`
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

## Cloud SQL

The application supports:

- local SQLite during development
- PostgreSQL in production

In Cloud Run, the app builds its database connection from:

- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `CLOUDSQL_CONNECTION_NAME`

## Google OAuth

Create a Google OAuth web client and add both local and hosted callbacks.

Typical values:

- local origin: `http://127.0.0.1:8000`
- local redirect: `http://127.0.0.1:8000/auth/google`
- production redirect: `https://<your-cloud-run-url>/auth/google`

Use `ALLOWED_GOOGLE_EMAIL` to restrict access to a single user.

## Notes

- `PUBLIC_BASE_URL` should match the external app URL if you use a custom domain or want explicit OAuth callback behavior.
- `max-instances=1` keeps the app simple for a single-user workflow and avoids multi-instance SQLite-style assumptions.
- Keep raw exports outside the repository and import them through the app.
