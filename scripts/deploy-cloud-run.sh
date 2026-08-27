#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Google Cloud Run Manual Deployment Script
# Enterprise HR Agentic Solution (MVP 1) - SDD §7.6 Fast-Path
# =============================================================================

PROJECT_ID="${PROJECT_ID:-pe-group5}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-hr-agentic-service}"
REPO_NAME="${REPO_NAME:-hr-agentic-repo}"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

echo "================================================================="
echo "🚀 Deploying HR Agentic Solution to Google Cloud Run"
echo "Project ID:    ${PROJECT_ID}"
echo "Region:        ${REGION}"
echo "Service Name:  ${SERVICE_NAME}"
echo "Target Image:  ${IMAGE_TAG}"
echo "================================================================="

# 1. Run local test validation
echo "▶ Running test suite before deployment..."
PYTHONPATH=HR-Agentic-Code python3 -m pytest HR-Agentic-Code/tests/ -q

# 2. Build and push container image using Cloud Build
echo "▶ Submitting container build to Google Cloud Build..."
gcloud builds submit HR-Agentic-Code \
  --tag "${IMAGE_TAG}" \
  --project "${PROJECT_ID}"

# 3. Deploy to Cloud Run
echo "▶ Deploying container image to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "SAAS_MCP_BASE_URL=https://mock-saas.aishprabhat.demo.altostrat.com,USE_LIVE_MCP=true,DEFAULT_CALLER_ID=EMP-509" \
  --set-secrets "SAAS_MCP_CREDENTIAL=saas-mcp-token:latest" \
  --port 8080


# 4. Verify deployment health
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --project "${PROJECT_ID}" --format 'value(status.url)')
echo "================================================================="
echo "✅ Deployment Successful!"
echo "Service URL: ${SERVICE_URL}"
echo "Testing health probe: ${SERVICE_URL}/health"
curl -s "${SERVICE_URL}/health" || true
echo ""
echo "================================================================="
