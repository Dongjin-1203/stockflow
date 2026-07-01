#!/bin/bash
set -e

PROJECT_ID=${GCP_PROJECT_ID:-"your-project-id"}
REGION="asia-northeast3"
SERVICE="demo-dashboard"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE"

echo "🔨 Docker 이미지 빌드 중..."
docker build -t $IMAGE .

echo "📤 이미지 푸시 중..."
docker push $IMAGE

echo "🚀 Cloud Run 배포 중..."
gcloud run deploy $SERVICE \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY,ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-claude-opus-4-8},DART_API_KEY=$DART_API_KEY,ECOS_API_KEY=$ECOS_API_KEY

URL=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')
echo "✅ 배포 완료!"
echo "🌐 URL: $URL"
