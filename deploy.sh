#!/bin/bash
# JARVIS Cloud Run Deployment Script
# Usage: ./deploy.sh [PROJECT_ID] [REGION] [SERVICE_NAME]

set -e

# Configuration
PROJECT_ID="${1:-gen-lang-client-0998294743}"
REGION="${2:-us-central1}"
SERVICE_NAME="${3:-jarvis-backend}"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/jarvis-repo/${SERVICE_NAME}"

echo "🚀 Deploying JARVIS to Google Cloud Run"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo "Image: ${IMAGE_NAME}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud. Run: gcloud auth login"
    exit 1
fi

# Set project
echo "📋 Setting project..."
gcloud config set project "${PROJECT_ID}"

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    texttospeech.googleapis.com \
    generativelanguage.googleapis.com

# Create Artifact Registry repository if it doesn't exist
echo "📦 Checking Artifact Registry..."
if ! gcloud artifacts repositories describe jarvis-repo --location="${REGION}" &>/dev/null; then
    echo "Creating Artifact Registry repository..."
    gcloud artifacts repositories create jarvis-repo \
        --repository-format=docker \
        --location="${REGION}" \
        --description="JARVIS Docker images"
fi

# Configure Docker for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build and push image using Cloud Build
echo "🏗️  Building and pushing Docker image..."
gcloud builds submit \
    --tag "${IMAGE_NAME}:latest" \
    --tag "${IMAGE_NAME}:$(date +%Y%m%d-%H%M%S)" \
    --project="${PROJECT_ID}"

# Create or update secret for Gemini API key
echo "🔐 Managing secrets..."
if ! gcloud secrets describe gemini-api-key --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating Gemini API key secret..."
    echo -n "Enter your Gemini API key: "
    read -s GEMINI_KEY
    echo ""
    echo -n "${GEMINI_KEY}" | gcloud secrets create gemini-api-key \
        --data-file=- \
        --project="${PROJECT_ID}"
else
    echo "Updating Gemini API key secret..."
    echo -n "Enter your Gemini API key (or press Enter to skip): "
    read -s GEMINI_KEY
    echo ""
    if [ -n "${GEMINI_KEY}" ]; then
        echo -n "${GEMINI_KEY}" | gcloud secrets versions add gemini-api-key \
            --data-file=- \
            --project="${PROJECT_ID}"
    fi
fi

# Grant Cloud Run service account access to secret
SERVICE_ACCOUNT="jarvis-cloud-run@${PROJECT_ID}.iam.gserviceaccount.com"
echo "🔑 Setting up service account permissions..."
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Creating service account..."
    gcloud iam service-accounts create jarvis-cloud-run \
        --display-name="JARVIS Cloud Run Service Account" \
        --project="${PROJECT_ID}"
fi

# Grant secret access
gcloud secrets add-iam-policy-binding gemini-api-key \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}"

# Grant Cloud TTS access
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudtexttospeech.user" \
    --quiet

# Deploy to Cloud Run
echo "☁️  Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_NAME}:latest" \
    --platform=managed \
    --region="${REGION}" \
    --service-account="${SERVICE_ACCOUNT}" \
    --allow-unauthenticated \
    --port=8080 \
    --memory=2Gi \
    --cpu=2 \
    --min-instances=0 \
    --max-instances=10 \
    --concurrency=80 \
    --timeout=300 \
    --set-env-vars="GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=gemini-api-key --project=${PROJECT_ID}),GOOGLE_CLOUD_PROJECT=${PROJECT_ID},CLOUD_DEPLOYMENT=true,MODEL_CACHE_DIR=/app/models" \
    --project="${PROJECT_ID}"

# Get service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --platform=managed \
    --region="${REGION}" \
    --format="value(status.url)" \
    --project="${PROJECT_ID}")

echo ""
echo "✅ Deployment complete!"
echo "🌐 Service URL: ${SERVICE_URL}"
echo ""
echo "📋 Next steps:"
echo "1. Update your frontend to use: ${SERVICE_URL}"
echo "2. Test the API: curl ${SERVICE_URL}/status"
echo "3. Configure custom domain (optional): gcloud run domain-mappings create --service=${SERVICE_NAME} --domain=jarvis.yourdomain.com --region=${REGION}"
echo ""
echo "📊 View logs: gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID}"