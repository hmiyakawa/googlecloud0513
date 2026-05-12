# ── ビルドステージ
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev

# ── 本番ステージ
FROM node:20-slim
WORKDIR /app

# セキュリティ：非 root ユーザーで実行
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./
COPY server.js ./
COPY public/ ./public/

USER appuser

# Cloud Run はデフォルトで PORT 環境変数を渡す
ENV PORT=8080
EXPOSE 8080

CMD ["node", "server.js"]
