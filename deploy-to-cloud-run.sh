#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy-to-cloud-run.sh <GCP_PROJECT> [REGION]
# Example: ./deploy-to-cloud-run.sh my-gcp-project us-central1

PROJECT=${1:-${GCP_PROJECT:-}}
REGION=${2:-${GCP_REGION:-us-central1}}
AR_REPOSITORY=${AR_REPOSITORY:-chatlium}
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPOSITORY}"

if [ -z "$PROJECT" ]; then
  echo "Usage: $0 <GCP_PROJECT> [REGION]"
  exit 1
fi

SERVICES=(Hospital_api RealEstate_api Restaurent_api School_api)
declare -A SVCNAME
SVCNAME[Hospital_api]=hospital-api
SVCNAME[RealEstate_api]=realestate-api
SVCNAME[Restaurent_api]=restaurent-api
SVCNAME[School_api]=school-api

# Ensure gcloud is authenticated and project is set
if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI not found. Install and authenticate first: https://cloud.google.com/sdk/docs/install"
  exit 2
fi

echo "Using project: $PROJECT, region: $REGION"

gcloud config set project "$PROJECT"

echo "Ensuring Artifact Registry repository exists: $AR_REPOSITORY"
if ! gcloud artifacts repositories describe "$AR_REPOSITORY" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPOSITORY" \
    --repository-format docker \
    --location "$REGION" \
    --description "Chatlium Cloud Run container images"
fi

ODOO_ENV_ARGS=()
if [ -z "${ODOO_DB_HOST:-}" ] && [ -n "${CLOUD_SQL_INSTANCE:-}" ]; then
  ODOO_DB_HOST="/cloudsql/${CLOUD_SQL_INSTANCE}"
fi

if [ -n "${ODOO_DB_HOST:-}" ] && [ -n "${ODOO_DB_USER:-}" ] && [ -n "${ODOO_DB_PASSWORD:-}" ]; then
  ODOO_ENV_ARGS+=(--set-env-vars "HOST=${ODOO_DB_HOST},USER=${ODOO_DB_USER},PASSWORD=${ODOO_DB_PASSWORD}")
else
  echo "Warning: ODOO_DB_HOST, ODOO_DB_USER, or ODOO_DB_PASSWORD is not set."
  echo "Deploying odoo-web without database env vars. Set them later with gcloud run services update."
fi

if [ -n "${CLOUD_SQL_INSTANCE:-}" ]; then
  ODOO_ENV_ARGS+=(--add-cloudsql-instances "$CLOUD_SQL_INSTANCE")
fi

ODOO_IMAGE="${IMAGE_BASE}/odoo-web:latest"

echo "\n--- Building Odoo -> ${ODOO_IMAGE} ---"
gcloud builds submit --config cloudbuild-odoo.yaml --substitutions "_IMAGE=${ODOO_IMAGE}" .

echo "--- Deploying odoo-web to Cloud Run ---"
gcloud run deploy odoo-web \
  --image "$ODOO_IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8069 \
  "${ODOO_ENV_ARGS[@]}"

ODOO_CLOUD_RUN_URL=$(gcloud run services describe odoo-web --region "$REGION" --format='value(status.url)')
echo "odoo-web deployed. View URL: $ODOO_CLOUD_RUN_URL"

API_ENV_VARS="ODOO_URL=$ODOO_CLOUD_RUN_URL,ODOO_DB=${ODOO_DB:-admin},ODOO_USER=${ODOO_USER:-api_user},ODOO_PASSWORD=${ODOO_PASSWORD:-api_password_123},JWT_SECRET=${JWT_SECRET:-supersecret123},SECRET_KEY=${SECRET_KEY:-supersecret123}"

for DIR in "${SERVICES[@]}"; do
  SVC=${SVCNAME[$DIR]}
  IMAGE="${IMAGE_BASE}/${SVC}:latest"
  echo "\n--- Building $DIR -> ${IMAGE} ---"
  gcloud builds submit --tag "$IMAGE" "$DIR"

  echo "--- Deploying $SVC to Cloud Run ---"
  gcloud run deploy "$SVC" \
    --image "$IMAGE" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8000 \
    --set-env-vars "$API_ENV_VARS"

  echo "$SVC deployed. View URL: $(gcloud run services describe "$SVC" --region "$REGION" --format='value(status.url)')"
done

echo "\nAll services deployed."
