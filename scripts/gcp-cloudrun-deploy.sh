#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-europe-west2}"
SERVICE_NAME="${SERVICE_NAME:-personal-finance}"
INSTANCE_NAME="${INSTANCE_NAME:-personal-finance-db}"
DB_NAME="${DB_NAME:-personal_finance}"
DB_USER="${DB_USER:-pfadmin}"
RUN_SA="${RUN_SA:-personal-finance-run@${PROJECT_ID}.iam.gserviceaccount.com}"
CONNECTION_NAME="${CONNECTION_NAME:-${PROJECT_ID}:${REGION}:${INSTANCE_NAME}}"
ALLOWED_GOOGLE_EMAIL="${ALLOWED_GOOGLE_EMAIL:-you@example.com}"
OWNER_LABEL="${OWNER_LABEL:-team-finance}"

gcloud run deploy "$SERVICE_NAME" \
  --quiet \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --service-account="$RUN_SA" \
  --allow-unauthenticated \
  --add-cloudsql-instances="$CONNECTION_NAME" \
  --set-env-vars="ALLOWED_GOOGLE_EMAIL=${ALLOWED_GOOGLE_EMAIL},ALLOW_DEV_LOGIN=0,DB_NAME=${DB_NAME},DB_USER=${DB_USER},CLOUDSQL_CONNECTION_NAME=${CONNECTION_NAME},HOST=0.0.0.0,OPENAI_MODEL=gpt-4.1-mini" \
  --set-secrets="APP_SECRET_KEY=personal-finance-app-secret:latest,GOOGLE_CLIENT_ID=personal-finance-google-client-id:latest,GOOGLE_CLIENT_SECRET=personal-finance-google-client-secret:latest,OPENAI_API_KEY=personal-finance-openai-key:latest,DB_PASSWORD=personal-finance-db-password:latest" \
  --max-instances=1 \
  --labels="project=personal-finance,environment=prod,owner=${OWNER_LABEL},managedby=codex,app=personal-finance"
