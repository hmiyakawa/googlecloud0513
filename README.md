# 翻訳チェッカー — Google Cloud Run デプロイガイド

日本語 → 任意言語 → 日本語のバックトランスレーションで翻訳品質を検証するツールです。

---

## アーキテクチャ

```
ブラウザ
  │  POST /api/translate
  ▼
Cloud Run（Node.js / Express）
  │  x-api-key ヘッダー（Secret Manager から注入）
  ▼
Anthropic API（Claude Sonnet）
```

APIキーはサーバー側の環境変数として管理し、ブラウザには一切露出しません。

---

## ファイル構成

```
translation-checker/
├── server.js          # Express サーバー（API プロキシ）
├── package.json
├── Dockerfile
├── .dockerignore
├── .env.example       # ローカル開発用テンプレート
├── deploy.sh          # Cloud Run 一括デプロイスクリプト
└── public/
    └── index.html     # フロントエンド（バニラ JS）
```

---

## ローカル開発

### 前提
- Node.js 18 以上
- Anthropic API キー

### 手順

```bash
# 1. 依存パッケージインストール
npm install

# 2. APIキーを設定
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を記入

# 3. 起動
npm run dev
# → http://localhost:8080 で確認
```

---

## Google Cloud Run デプロイ

### 前提条件

| ツール | インストール方法 |
|--------|----------------|
| gcloud CLI | https://cloud.google.com/sdk/docs/install |
| Docker | https://docs.docker.com/get-docker/ |

### 手順

**① gcloud にログイン**
```bash
gcloud auth login
gcloud auth configure-docker
```

**② deploy.sh を編集**
```bash
# deploy.sh の冒頭にある変数を自分の環境に合わせて変更
PROJECT_ID="your-project-id"   # ← GCP プロジェクト ID
REGION="asia-northeast1"       # 東京リージョン（変更可）
```

**③ APIキーをシェル変数にセット**
```bash
export ANTHROPIC_API_KEY="sk-ant-xxxxxxxxxx"
```

**④ デプロイ実行**
```bash
chmod +x deploy.sh
./deploy.sh
```

デプロイ完了後に URL が表示されます：
```
✅ デプロイ完了！
🌐 URL: https://translation-checker-xxxx-an.a.run.app
```

---

## 手動デプロイ（ステップごと）

```bash
PROJECT_ID="your-project-id"
REGION="asia-northeast1"
SERVICE="translation-checker"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

# コンテナビルド & プッシュ
gcloud builds submit --tag "${IMAGE}" .

# Secret Manager にAPIキー登録
echo -n "${ANTHROPIC_API_KEY}" | \
  gcloud secrets create anthropic-api-key --data-file=- --replication-policy=automatic

# Cloud Run デプロイ
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 10
```

---

## APIキーの更新

```bash
# 新しいバージョンを追加
echo -n "sk-ant-新しいキー" | \
  gcloud secrets versions add anthropic-api-key --data-file=-

# Cloud Run を再デプロイ（最新バージョンを自動参照）
gcloud run deploy translation-checker --region asia-northeast1 --image gcr.io/PROJECT_ID/translation-checker
```

---

## コスト目安（東京リージョン）

| リソース | 料金 |
|---------|------|
| Cloud Run（リクエスト） | 200万回/月まで無料 |
| Cloud Run（CPU/メモリ） | リクエスト処理中のみ課金 |
| Container Registry | 0.5GB まで無料 |
| Secret Manager | 6シークレット/月まで無料 |
| **Anthropic API** | 翻訳1回あたり約 $0.001〜0.003 |

社内利用（数十人規模）であれば Cloud Run の料金はほぼ無料枠内に収まります。

---

## 社内利用での追加設定（任意）

### アクセス制限（社内のみ）
```bash
# --allow-unauthenticated を削除し、IAP（Identity-Aware Proxy）を設定
gcloud run deploy translation-checker \
  --no-allow-unauthenticated \
  ...
```

### カスタムドメイン
```bash
gcloud run domain-mappings create \
  --service translation-checker \
  --domain translate.your-company.com \
  --region asia-northeast1
```

---

## トラブルシューティング

| エラー | 原因 | 対処 |
|--------|------|------|
| `ERROR: ANTHROPIC_API_KEY が設定されていません` | 環境変数未設定 | Secret Manager の設定を確認 |
| `HTTP 502` | Anthropic API エラー | APIキーの有効性・残高を確認 |
| `Container failed to start` | ポート設定ミス | `PORT=8080` が正しいか確認 |
| ビルドエラー | Docker 未起動 | Docker Desktop を起動 |
