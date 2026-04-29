# Runbook

This runbook covers the routine operational checks for the hosted app.

## Hosted Shape

- GCP project: `personal-finance-wm-2026`
- Cloud Run service: `personal-finance`
- Cloud SQL instance: `personal-finance-db`
- Region: `europe-west2`

## Health Check

Check the app responds:

```bash
curl -I https://<your-cloud-run-url>/
```

Check the deployed Cloud Run service:

```bash
gcloud run services describe personal-finance \
  --project "$PROJECT_ID" \
  --region europe-west2
```

## Deploy

From the repo root:

```bash
./scripts/gcp-cloudrun-deploy.sh
```

## Gcloud Auth Checklist

Before asking Codex to deploy or inspect production:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project personal-finance-wm-2026
```

For Codex-driven commands, prefer:

```bash
./scripts/gcloud-codex.sh auth list --filter=status:ACTIVE
./scripts/gcloud-codex.sh config get-value project
```

If Codex reports auth refresh errors:

1. refresh `gcloud` credentials in a normal local shell
2. verify the active project is still `personal-finance-wm-2026`
3. retry the command through `./scripts/gcloud-codex.sh`

If Codex reports DNS or connection errors to Google APIs, the problem is session network access, not the stored credentials.

## Logs

Read recent Cloud Run logs:

```bash
gcloud run services logs read personal-finance \
  --project "$PROJECT_ID" \
  --region europe-west2 \
  --limit=200
```

## Nightly Database Backups

Nightly backups are handled by Cloud SQL automated backups.

Expected baseline:

- backups enabled
- backup start time `03:00`
- `7` retained backups

Verify:

```bash
gcloud sql instances describe personal-finance-db \
  --project "$PROJECT_ID" \
  --format='json(settings.backupConfiguration)'
```

If needed, update backup schedule/retention:

```bash
gcloud sql instances patch personal-finance-db \
  --project "$PROJECT_ID" \
  --backup-start-time=03:00 \
  --retained-backups-count=7 \
  --quiet
```

## Restore Readiness

At least occasionally, verify that:

1. backups still exist in Cloud SQL
2. the instance reports backups as enabled
3. you know which project and region hold the production instance

## Secrets

The hosted app expects these Secret Manager entries:

- `personal-finance-app-secret`
- `personal-finance-google-client-id`
- `personal-finance-google-client-secret`
- `personal-finance-openai-key`
- `personal-finance-db-password`
