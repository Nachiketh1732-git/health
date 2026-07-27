#!/usr/bin/env bash
# Deploys both services to Cloud Run. Safe to re-run — every command is
# idempotent, so this doubles as your redeploy script.
#
#   ./deploy/deploy.sh my-project-id
#
set -euo pipefail

PROJECT="${1:?Usage: ./deploy/deploy.sh <gcp-project-id>}"
REGION="${REGION:-asia-south1}"          # Mumbai — closest to you
VERTEX_REGION="${VERTEX_REGION:-asia-south1}"
REPO="wellness"
API_SVC="wellness-api"
WEB_SVC="wellness-web"
SA="wellness-run"

echo "==> Project $PROJECT / region $REGION"
gcloud config set project "$PROJECT" --quiet

echo "==> Enabling APIs (first run takes a couple of minutes)"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  identitytoolkit.googleapis.com --quiet

echo "==> Artifact Registry"
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION" \
  --description="Wellness platform images" --quiet 2>/dev/null || echo "    exists, skipping"

echo "==> Firestore (Native mode)"
gcloud firestore databases create --location="$REGION" --type=firestore-native --quiet \
  2>/dev/null || echo "    exists, skipping"

echo "==> Runtime service account"
gcloud iam service-accounts create "$SA" --display-name="Wellness Cloud Run" --quiet \
  2>/dev/null || echo "    exists, skipping"

SA_EMAIL="${SA}@${PROJECT}.iam.gserviceaccount.com"
for ROLE in roles/datastore.user roles/aiplatform.user roles/firebaseauth.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" --role="$ROLE" \
    --condition=None --quiet >/dev/null
done
echo "    bound datastore.user, aiplatform.user, firebaseauth.viewer"

BASE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"

echo "==> Building API image"
gcloud builds submit backend --tag "${BASE}/${API_SVC}:latest" --quiet

echo "==> Deploying API"
gcloud run deploy "$API_SVC" \
  --image "${BASE}/${API_SVC}:latest" \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT},VERTEX_LOCATION=${VERTEX_REGION},VERTEX_MODEL=gemini-2.0-flash" \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 5 \
  --quiet

API_URL="$(gcloud run services describe "$API_SVC" --region "$REGION" --format='value(status.url)')"
echo "    API live at $API_URL"

echo "==> Building web image"
gcloud builds submit frontend \
  --substitutions "_API_BASE=${API_URL},_FB_KEY=${VITE_FIREBASE_API_KEY:-},_FB_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN:-},_FB_PROJECT=${PROJECT}" \
  --config deploy/cloudbuild-web.yaml --quiet

echo "==> Deploying web"
gcloud run deploy "$WEB_SVC" \
  --image "${BASE}/${WEB_SVC}:latest" \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 256Mi --cpu 1 --min-instances 0 --max-instances 5 \
  --quiet

WEB_URL="$(gcloud run services describe "$WEB_SVC" --region "$REGION" --format='value(status.url)')"

echo "==> Locking API CORS to the web origin"
gcloud run services update "$API_SVC" --region "$REGION" \
  --update-env-vars "ALLOWED_ORIGINS=${WEB_URL}" --quiet

echo
echo "Done."
echo "  Dashboard : $WEB_URL"
echo "  API       : $API_URL"
echo
echo "Last step, in the console: Firebase Auth -> Sign-in method -> enable Google,"
echo "then add ${WEB_URL#https://} under Authorized domains."
