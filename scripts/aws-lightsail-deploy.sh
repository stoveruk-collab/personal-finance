#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f ".env.aws" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.aws"
  set +a
fi

AWS_REGION="${AWS_REGION:-eu-west-2}"
SERVICE_NAME="${SERVICE_NAME:-personal-finance}"
CONTAINER_LABEL="${CONTAINER_LABEL:-app}"
LOCAL_IMAGE_NAME="${LOCAL_IMAGE_NAME:-personal-finance:lightsail}"
IMAGE_PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
CONTAINER_POWER="${CONTAINER_POWER:-nano}"
CONTAINER_SCALE="${CONTAINER_SCALE:-1}"
DB_RESOURCE_NAME="${DB_RESOURCE_NAME:-personal-finance-db}"
DB_ENGINE="${DB_ENGINE:-postgres}"
MASTER_DATABASE_NAME="${MASTER_DATABASE_NAME:-personal_finance}"
MASTER_USERNAME="${MASTER_USERNAME:-pfadmin}"
PROJECT_TAG="${PROJECT_TAG:-personal-finance}"
ENVIRONMENT_TAG="${ENVIRONMENT_TAG:-prod}"
OWNER_TAG="${OWNER_TAG:-${ALLOWED_GOOGLE_EMAIL:-team-finance@example.com}}"
MANAGED_BY_TAG="${MANAGED_BY_TAG:-codex}"
BOOTSTRAP_ENV_FILE="${BOOTSTRAP_ENV_FILE:-$PROJECT_ROOT/.data/aws/lightsail-bootstrap.env}"

mkdir -p "$(dirname "$BOOTSTRAP_ENV_FILE")"

usage() {
  cat <<'EOF'
Usage:
  scripts/aws-lightsail-deploy.sh bootstrap
  scripts/aws-lightsail-deploy.sh deploy
  scripts/aws-lightsail-deploy.sh status

Environment:
  Put app secrets in .env.aws or export them in your shell.
  Required for deploy: APP_SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
}

resource_tags() {
  TAG_ARGS=(
    "key=Project,value=${PROJECT_TAG}"
    "key=Environment,value=${ENVIRONMENT_TAG}"
    "key=Owner,value=${OWNER_TAG}"
    "key=ManagedBy,value=${MANAGED_BY_TAG}"
    "key=App,value=personal-finance"
  )
}

write_bootstrap_env() {
  umask 077
  cat >"$BOOTSTRAP_ENV_FILE" <<EOF
AWS_REGION=${AWS_REGION}
SERVICE_NAME=${SERVICE_NAME}
DB_RESOURCE_NAME=${DB_RESOURCE_NAME}
MASTER_DATABASE_NAME=${MASTER_DATABASE_NAME}
MASTER_USERNAME=${MASTER_USERNAME}
DB_MASTER_PASSWORD=${DB_MASTER_PASSWORD}
PROJECT_TAG=${PROJECT_TAG}
ENVIRONMENT_TAG=${ENVIRONMENT_TAG}
OWNER_TAG=${OWNER_TAG}
EOF
}

generate_password() {
  python3 - <<'PY'
import secrets
alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_"
print("".join(secrets.choice(alphabet) for _ in range(32)))
PY
}

choose_db_blueprint() {
  aws lightsail get-relational-database-blueprints \
    --region "$AWS_REGION" \
    --output json |
    python3 -c '
import json, re, sys
items = [b for b in json.load(sys.stdin)["blueprints"] if b.get("engine") == "postgres"]
if not items:
    raise SystemExit("No PostgreSQL blueprints available in this region.")
def version_key(item):
    match = re.search(r"(\d+)$", item["blueprintId"])
    return int(match.group(1)) if match else -1
items.sort(key=version_key)
print(items[-1]["blueprintId"])
'
}

choose_db_bundle() {
  aws lightsail get-relational-database-bundles \
    --region "$AWS_REGION" \
    --output json |
    python3 -c '
import json, sys
items = json.load(sys.stdin)["bundles"]
if not items:
    raise SystemExit("No relational database bundles available in this region.")
items.sort(key=lambda item: float(item.get("price", 0)))
print(items[0]["bundleId"])
'
}

database_exists() {
  aws lightsail get-relational-database \
    --region "$AWS_REGION" \
    --relational-database-name "$DB_RESOURCE_NAME" \
    >/dev/null 2>&1
}

container_service_exists() {
  aws lightsail get-container-services \
    --region "$AWS_REGION" \
    --service-name "$SERVICE_NAME" \
    --query 'containerServices[0].containerServiceName' \
    --output text >/dev/null 2>&1
}

wait_for_database() {
  echo "Waiting for Lightsail database ${DB_RESOURCE_NAME}..."
  while true; do
    state="$(
      aws lightsail get-relational-database \
        --region "$AWS_REGION" \
        --relational-database-name "$DB_RESOURCE_NAME" \
        --query 'relationalDatabase.state' \
        --output text
    )"
    if [[ "$state" == "available" ]]; then
      break
    fi
    sleep 15
  done
}

wait_for_service() {
  echo "Waiting for container service ${SERVICE_NAME}..."
  while true; do
    state="$(
      aws lightsail get-container-services \
        --region "$AWS_REGION" \
        --service-name "$SERVICE_NAME" \
        --query 'containerServices[0].state' \
        --output text
    )"
    if [[ "$state" == "READY" || "$state" == "RUNNING" ]]; then
      break
    fi
    sleep 10
  done
}

db_endpoint() {
  aws lightsail get-relational-database \
    --region "$AWS_REGION" \
    --relational-database-name "$DB_RESOURCE_NAME" \
    --query 'relationalDatabase.masterEndpoint.address' \
    --output text
}

service_url() {
  aws lightsail get-container-services \
    --region "$AWS_REGION" \
    --service-name "$SERVICE_NAME" \
    --query 'containerServices[0].url' \
    --output text
}

bootstrap() {
  require_command aws
  require_command docker
  local TAG_ARGS=()

  if [[ -z "${DB_MASTER_PASSWORD:-}" ]]; then
    DB_MASTER_PASSWORD="$(generate_password)"
  fi
  export DB_MASTER_PASSWORD
  resource_tags

  if ! database_exists; then
    DB_BLUEPRINT_ID="${DB_BLUEPRINT_ID:-$(choose_db_blueprint)}"
    DB_BUNDLE_ID="${DB_BUNDLE_ID:-$(choose_db_bundle)}"
    echo "Creating tagged Lightsail database ${DB_RESOURCE_NAME} in ${AWS_REGION}..."
    aws lightsail create-relational-database \
      --region "$AWS_REGION" \
      --relational-database-name "$DB_RESOURCE_NAME" \
      --relational-database-blueprint-id "$DB_BLUEPRINT_ID" \
      --relational-database-bundle-id "$DB_BUNDLE_ID" \
      --master-database-name "$MASTER_DATABASE_NAME" \
      --master-username "$MASTER_USERNAME" \
      --master-user-password "$DB_MASTER_PASSWORD" \
      --no-publicly-accessible \
      --tags "${TAG_ARGS[@]}"
    wait_for_database
  else
    echo "Database ${DB_RESOURCE_NAME} already exists; leaving it in place."
  fi

  if ! container_service_exists; then
    echo "Creating tagged Lightsail container service ${SERVICE_NAME} in ${AWS_REGION}..."
    aws lightsail create-container-service \
      --region "$AWS_REGION" \
      --service-name "$SERVICE_NAME" \
      --power "$CONTAINER_POWER" \
      --scale "$CONTAINER_SCALE" \
      --tags "${TAG_ARGS[@]}"
    wait_for_service
  else
    echo "Container service ${SERVICE_NAME} already exists; leaving it in place."
  fi

  write_bootstrap_env
  echo "Bootstrap complete."
  echo "Saved reusable resource settings to ${BOOTSTRAP_ENV_FILE}"
  echo "Database endpoint: $(db_endpoint)"
  echo "Container service URL: $(service_url)"
}

deploy() {
  require_command aws
  require_command docker
  require_env APP_SECRET_KEY
  require_env GOOGLE_CLIENT_ID
  require_env GOOGLE_CLIENT_SECRET
  require_env OPENAI_API_KEY

  if ! database_exists || ! container_service_exists; then
    echo "Resources do not exist yet. Run: scripts/aws-lightsail-deploy.sh bootstrap" >&2
    exit 1
  fi

  require_env DB_MASTER_PASSWORD
  local db_host
  db_host="$(db_endpoint)"

  local encoded_password database_url deployment_json
  encoded_password="$(
    DB_MASTER_PASSWORD="$DB_MASTER_PASSWORD" python3 - <<'PY'
import os
from urllib.parse import quote_plus
print(quote_plus(os.environ["DB_MASTER_PASSWORD"]))
PY
  )"
  database_url="postgresql+psycopg://${MASTER_USERNAME}:${encoded_password}@${db_host}:5432/${MASTER_DATABASE_NAME}?sslmode=require"

  echo "Building container image ${LOCAL_IMAGE_NAME} for ${IMAGE_PLATFORM}..."
  docker build --platform "$IMAGE_PLATFORM" -t "$LOCAL_IMAGE_NAME" .

  echo "Pushing image into Lightsail service registry..."
  aws lightsail push-container-image \
    --region "$AWS_REGION" \
    --service-name "$SERVICE_NAME" \
    --image "$LOCAL_IMAGE_NAME" \
    --label "$CONTAINER_LABEL" >/dev/null

  deployment_json="$(mktemp)"
  SERVICE_NAME="$SERVICE_NAME" \
  CONTAINER_LABEL="$CONTAINER_LABEL" \
  APP_SECRET_KEY="$APP_SECRET_KEY" \
  DATABASE_URL="$database_url" \
  GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
  GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET" \
  ALLOWED_GOOGLE_EMAIL="${ALLOWED_GOOGLE_EMAIL:-you@example.com}" \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  OPENAI_MODEL="${OPENAI_MODEL:-gpt-4.1-mini}" \
  ALLOW_DEV_LOGIN="${ALLOW_DEV_LOGIN:-0}" \
  PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}" \
  python3 - <<'PY' >"$deployment_json"
import json
import os

deployment = {
    "app": {
        "image": f":{os.environ['SERVICE_NAME']}.{os.environ['CONTAINER_LABEL']}.latest",
        "environment": {
            "APP_SECRET_KEY": os.environ["APP_SECRET_KEY"],
            "DATABASE_URL": os.environ["DATABASE_URL"],
            "GOOGLE_CLIENT_ID": os.environ["GOOGLE_CLIENT_ID"],
            "GOOGLE_CLIENT_SECRET": os.environ["GOOGLE_CLIENT_SECRET"],
            "ALLOWED_GOOGLE_EMAIL": os.environ["ALLOWED_GOOGLE_EMAIL"],
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
            "OPENAI_MODEL": os.environ["OPENAI_MODEL"],
            "ALLOW_DEV_LOGIN": os.environ["ALLOW_DEV_LOGIN"],
            "PUBLIC_BASE_URL": os.environ["PUBLIC_BASE_URL"],
            "HOST": "0.0.0.0",
            "PORT": "8000",
        },
        "ports": {"8000": "HTTP"},
    }
}
endpoint = {
    "containerName": "app",
    "containerPort": 8000,
    "healthCheck": {
        "path": "/healthz",
        "intervalSeconds": 10,
        "timeoutSeconds": 5,
        "healthyThreshold": 2,
        "unhealthyThreshold": 2,
        "successCodes": "200-299",
    },
}
print(json.dumps({"serviceName": os.environ["SERVICE_NAME"], "containers": deployment, "publicEndpoint": endpoint}))
PY

  echo "Creating Lightsail deployment..."
  aws lightsail create-container-service-deployment \
    --region "$AWS_REGION" \
    --cli-input-json "file://${deployment_json}" >/dev/null

  rm -f "$deployment_json"
  wait_for_service

  echo "Deployment submitted."
  echo "App URL: $(service_url)"
}

status() {
  require_command aws
  echo "Region: ${AWS_REGION}"
  if database_exists; then
    echo "Database: ${DB_RESOURCE_NAME}"
    echo "  Endpoint: $(db_endpoint)"
    aws lightsail get-relational-database \
      --region "$AWS_REGION" \
      --relational-database-name "$DB_RESOURCE_NAME" \
      --query 'relationalDatabase.{State:state,Engine:engine,Bundle:bundleId}' \
      --output table
  else
    echo "Database: not created"
  fi

  if container_service_exists; then
    echo "Service: ${SERVICE_NAME}"
    echo "  URL: $(service_url)"
    aws lightsail get-container-services \
      --region "$AWS_REGION" \
      --service-name "$SERVICE_NAME" \
      --query 'containerServices[0].{State:state,Power:power,Scale:scale,URL:url}' \
      --output table
  else
    echo "Service: not created"
  fi
}

main() {
  local command="${1:-}"
  case "$command" in
    bootstrap) bootstrap ;;
    deploy) deploy ;;
    status) status ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
