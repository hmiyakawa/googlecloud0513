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
    ├── fileshare.py
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
   pip3 install -r requirements.txt --break-system-packages
   ```

3. `.env.example` をコピーして `.env` を作り、`SECRET_KEY` と `ADMIN_PASSWORD` を自分の値に変更する

   ```
   cp .env.example .env
   ```

4. 起動する

   ```
   python3 fileshare.py
   ```

   `http://localhost:8082` にアクセスして、ログイン画面が出れば成功です。

## コードを更新して本番サーバー（VM）に反映する手順

コードを直したいときは、いつも以下の流れになります。「ローカル(自分のMac)で直す → GitHubに送る → VM(Compute Engine)で最新版を取り込んで再起動」の3ステップです。

### 1. ローカル(Mac)でファイルを編集する

VS Codeやテキストエディタで、直したいファイル(例: `app2/file-share/fileshare.py`)を編集して保存する。

### 2. GitHubに反映する（ターミナルまたはVS Code）

ターミナルの場合:

```
cd /Users/hiroshim/Documents/googlecloud0513
git add app2
git commit -m "変更内容を書く（例: file-shareの管理画面を修正）"
git push origin main
```

VS Codeの場合は、ソース管理パネルでコミットメッセージを入力して「コミット」→「Sync Changes（プッシュ）」でも同じことができます。

### 3. VM（Compute Engine）に最新版を取り込む

GCPコンソール → Compute Engine → 対象のVMの「SSH」ボタンでブラウザターミナルを開き、以下を実行する。

```
cd /home/hiroshi_miyakawa/googlecloud0513
git pull origin main
```

その後、変更したアプリだけを再起動する。

| アプリ | pm2でのプロセス名 | 再起動コマンド |
|---|---|---|
| 要約・英訳ツール | `summarizer` | `pm2 restart summarizer` |
| 翻訳チェッカー | `translation-checker` | `pm2 restart translation-checker` |
| ファイル共有ツール | `file-share` | `pm2 restart file-share` |

Node.jsのアプリ(summarize-tool, translate-checker)で新しいライブラリを追加した場合は、再起動の前にそのフォルダで `npm install` が必要です。Pythonのアプリ(file-share)で `requirements.txt` を変更した場合は、再起動の前に `pip3 install -r requirements.txt --break-system-packages` が必要です。

### 4. 確認する

再起動後、ログにエラーが出ていないか確認する。

```
pm2 logs <プロセス名> --lines 30
```

問題なければ、ブラウザで該当のURL(`http://tools.ad-comm.com:8080/8081/8082`)を開いて動作を確認する。

## 今回何が起きていたか（簡単な説明）

- summarize.html を使う新しいアプリ用の server.js（PDF/Word抽出・要約・英訳の3機能）
- index.html を使う古いアプリ用の server.js（英訳のみのシンプル版）

この2つが同じフォルダに一緒に置かれていたため、「server.jsが2つ」に見えていました。中身も設定（ポート番号、参照するhtml、依存ライブラリ）も違うので、統合はせずフォルダを分けています。
