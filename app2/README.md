# フォルダ整理後の構成

server.js が2つあった理由は、実は「別々の2つのアプリ」のファイルが1つのフォルダに混在していたためでした。それぞれ専用フォルダに分けました。

```
app2/
├── summarize-tool/       ← 要約・英訳ツール（summarize.html）
│   ├── server.js
│   ├── package.json
│   ├── .env.example
│   ├── routes/
│   │   └── summarizeTranslate.js
│   └── public/
│       └── summarize.html
│
├── translate-checker/    ← 翻訳チェッカー（index.html）
│   ├── server.js
│   ├── package.json
│   ├── .env.example
│   └── public/
│       └── index.html
│
└── file-share/           ← ファイル共有ツール（Python/Flask）
    ├── AD_File_share.py
    ├── requirements.txt
    └── .env.example
```

## 起動方法（各アプリ共通の手順）

はじめて起動するときだけ、下の準備が必要です。

1. ターミナル（Macなら「ターミナル」アプリ）を開く
2. 起動したいアプリのフォルダに移動する

   ```
   cd 選んだフォルダのパス/summarize-tool
   ```

   （translate-checker を動かす場合は `translate-checker` に読み替え）

3. 必要な部品（ライブラリ）を1回だけインストールする

   ```
   npm install
   ```

4. `.env.example` をコピーして `.env` という名前で保存し、値を埋める

   ```
   cp .env.example .env
   ```

   `.env` の中身（ANTHROPIC_API_KEY、GOOGLE_CLIENT_ID など）は、今までお使いだった値をそのまま入れてください。

5. サーバーを起動する

   ```
   npm start
   ```

   「✅ ... 起動」と表示されれば成功です。ブラウザで `http://localhost:8081`（summarize-tool）または `http://localhost:8080`（translate-checker）にアクセスできます。

## 2つを同時に動かす場合

ポート番号は元から 8081（要約・英訳ツール）と 8080（翻訳チェッカー）で別々になっているので、2つのターミナルウィンドウでそれぞれ `npm start` すれば同時に動かせます。

Google Cloud Console 側のOAuth設定に、2つのコールバックURL
`http://tools.ad-comm.com:8081/auth/callback` と
`http://tools.ad-comm.com:8080/auth/callback`
の両方が登録されているか一度確認してください。

## file-share（ファイル共有ツール）の起動方法

こちらはPython(Flask)製で、他の2つ(Node.js)とは仕組みが異なります。

1. フォルダに移動する

   ```
   cd 選んだフォルダのパス/file-share
   ```

2. 必要なライブラリをインストールする（初回のみ）

   ```
   pip install -r requirements.txt
   ```

3. `.env.example` をコピーして `.env` を作り、`SECRET_KEY` と `ADMIN_PASSWORD` を自分の値に変更する

   ```
   cp .env.example .env
   ```

4. 起動する

   ```
   python3 AD_File_share.py
   ```

   `http://localhost:8082` にアクセスして、ログイン画面が出れば成功です。

## 今回何が起きていたか（簡単な説明）

- summarize.html を使う新しいアプリ用の server.js（PDF/Word抽出・要約・英訳の3機能）
- index.html を使う古いアプリ用の server.js（英訳のみのシンプル版）

この2つが同じフォルダに一緒に置かれていたため、「server.jsが2つ」に見えていました。中身も設定（ポート番号、参照するhtml、依存ライブラリ）も違うので、統合はせずフォルダを分けています。
