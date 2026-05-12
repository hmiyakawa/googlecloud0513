#!/bin/bash
# ================================================================
# Cloud Run デプロイスクリプト
# 実行前に gcloud CLI のインストールと認証を済ませてください
# ================================================================
set -e

# ── 設定（必要に応じて変更）──────────────────────────────────
PROJECT_ID="your-project-id"          # GCP プロジェクト ID
REGION="asia-northeast1"              # 東京リージョン
SERVICE_NAME="translation-checker"   # Cloud Run サービス名
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
SECRET_NAME="anthropic-api-key"       # Secret Manager のシークレット名
# ─────────────────────────────────────────────────────────────

echo "🔧 プロジェクト設定: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

# 1. 必要な API を有効化
echo "🔌 API を有効化中..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com

# 2. APIキーを Secret Manager に登録（初回のみ）
if ! gcloud secrets describe "${SECRET_NAME}" &>/dev/null; then
  echo "🔑 Secret Manager にAPIキーを登録します..."
  echo -n "${ANTHROPIC_API_KEY}" | \
    gcloud secrets create "${SECRET_NAME}" \
      --data-file=- \
      --replication-policy="automatic"
  echo "✅ シークレット登録完了"
else
  echo "ℹ️  シークレットは既に存在します（スキップ）"
fi

# 3. Cloud Build でコンテナをビルド & Container Registry にプッシュ
echo "🏗️  コンテナをビルド中..."
gcloud builds submit --tag "${IMAGE}" .

# 4. Cloud Run にデプロイ
echo "🚀 Cloud Run にデプロイ中..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-secrets "ANTHROPIC_API_KEY=${SECRET_NAME}:latest" \
  --memory 256Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 80 \
  --timeout 60

# 5. デプロイ先 URL を表示
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --platform managed \
  --region "${REGION}" \
  --format "value(status.url)")

echo ""
echo "✅ デプロイ完了！"
echo "🌐 URL: ${URL}"
