# -*- coding: utf-8 -*-
"""
ファイル共有ツール（第2版）

できること：
  - アップロードする人：ad-comm.com のGoogleアカウントでログインが必要
  - ダウンロードする人：アカウント登録は不要。ファイルごとに設定されたID/パスワードを
    知っていれば誰でもダウンロードできる
  - アップロード時に、そのファイル専用のダウンロード用ID/パスワードを自分で決める
  - 自分がアップロードしたファイルは自分で削除できる

必要なもの：
  - Python 3.9 以上
  - Flask, python-dotenv, requests-oauthlib
    （pip install -r requirements.txt でインストール）

起動設定（.env で変更可能。詳しくは .env.example を参照）：
  - PORT                  : 待ち受けポート（デフォルト 8082）
  - SECRET_KEY            : セッション暗号化キー（公開前に必ず変更してください）
  - ADMIN_USERNAME        : 管理画面ログインID（デフォルト admin）
  - ADMIN_PASSWORD        : 管理画面初期パスワード（公開前に必ず変更してください）
  - GOOGLE_CLIENT_ID      : Google OAuth クライアントID
  - GOOGLE_CLIENT_SECRET  : Google OAuth クライアントシークレット
  - ALLOWED_GOOGLE_DOMAIN : アップロードを許可するGoogleドメイン（デフォルト ad-comm.com）
  - BASE_URL              : このアプリの外部URL（例: http://tools.ad-comm.com:8082）
"""

import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, send_from_directory, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from requests_oauthlib import OAuth2Session

load_dotenv()  # 同じフォルダの .env を読み込む

# ---- 基本設定 --------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")    # 実ファイルの保存先フォルダ
DB_PATH = os.path.join(BASE_DIR, "database.db")   # ファイル情報のデータベース
MAX_CONTENT_LENGTH = 1024 * 1024 * 1024           # 1ファイルの上限（1GB）

PORT = int(os.environ.get("PORT", 8082))

# 管理画面用アカウント（.env の ADMIN_USERNAME / ADMIN_PASSWORD で上書きできます。
# 公開前に必ず変更してください）
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")

# ---- Google OAuth 設定（アップロードするための本人確認専用） ----------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
ALLOWED_GOOGLE_DOMAIN = os.environ.get("ALLOWED_GOOGLE_DOMAIN", "ad-comm.com")
BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{PORT}")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/google/callback"

# ローカルの http でOAuthをテストする場合に必要（本番のhttpsでは不要）
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

os.makedirs(UPLOAD_DIR, exist_ok=True)            # uploads フォルダが無ければ自動作成

app = Flask(__name__)
# ↓ セッションを暗号化する鍵。.env の SECRET_KEY で上書きできます。公開前に必ず変更してください。
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-please")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


# ---- データベース ----------------------------------------------------------
def get_db():
    """データベースへ接続する（1回の処理ごとに開いて閉じる）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 列名で値を取り出せるようにする
    return conn


def init_db():
    """最初に一度だけ、必要な表（テーブル）を作る"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            stored_name    TEXT NOT NULL,   -- 保存時の実ファイル名（重複防止のためUUID付き）
            original_name  TEXT NOT NULL,   -- 元のファイル名（表示・DL用）
            uploader_email TEXT NOT NULL,   -- アップロードしたGoogleアカウントのメールアドレス
            download_id    TEXT UNIQUE NOT NULL, -- ダウンロード用ID（相手に伝える名前）
            password_hash  TEXT NOT NULL,   -- ダウンロード用パスワードの暗号化済みハッシュ
            uploaded_at    TEXT NOT NULL,   -- アップロード日時
            size           INTEGER NOT NULL -- ファイルサイズ（バイト）
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---- アップロードする人（Googleログイン）のための制限 ----------------------
def uploader_required(view):
    """アップロード関連の画面はGoogleでログイン済みの人だけが使える"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "uploader_email" not in session:
            return redirect(url_for("uploader_login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """管理画面はID/パスワードでログインした管理者だけが使える"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# ---- ファイルサイズを読みやすく表示するための補助 --------------------------
@app.template_filter("filesize")
def filesize(num):
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


# ---- 画面の共通部分（デザイン） --------------------------------------------
PAGE_TOP = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ファイル共有ツール</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,"Hiragino Kaku Gothic ProN","Meiryo",sans-serif;
         background:#f4f6f8; color:#1f2933; }
  .topbar { display:flex; justify-content:space-between; align-items:center;
            background:#2563eb; color:#fff; padding:14px 20px; }
  .brand { font-weight:bold; font-size:18px; color:#fff; text-decoration:none; }
  .topbar nav a { color:#fff; margin-left:14px; text-decoration:none; }
  .topbar .user { opacity:.9; margin-left:8px; }
  main { max-width:820px; margin:24px auto; padding:0 16px; }
  .card { background:#fff; border:1px solid #e5e7eb; border-radius:10px;
          padding:20px; margin-bottom:20px; }
  .card h2 { margin-top:0; font-size:16px; }
  .flash { background:#fef3c7; border:1px solid #fcd34d; border-radius:8px;
           padding:10px 14px; margin-bottom:16px; font-size:14px; }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:10px; border-bottom:1px solid #eef2f7; font-size:14px; }
  th { color:#6b7280; font-weight:600; }
  .actions { white-space:nowrap; text-align:right; }
  a.btn-download { background:#2563eb; color:#fff; padding:5px 10px; border-radius:6px;
                   text-decoration:none; font-size:13px; }
  .btn-delete { background:#ef4444; color:#fff; border:none; padding:5px 10px;
                border-radius:6px; cursor:pointer; font-size:13px; margin-left:6px; }
  button { background:#2563eb; color:#fff; border:none; padding:9px 16px;
           border-radius:6px; cursor:pointer; font-size:14px; }
  .upload-form { display:flex; flex-direction:column; gap:12px; max-width:420px; }
  .upload-form label { font-size:14px; }
  .upload-form input { display:block; width:100%; padding:9px; margin-top:4px;
                border:1px solid #d1d5db; border-radius:6px; font-size:14px; }
  .hint, .empty { color:#6b7280; font-size:13px; }
  .auth { max-width:360px; margin:0 auto; }
  .auth label { display:block; margin-bottom:12px; font-size:14px; }
  .auth input { display:block; width:100%; padding:9px; margin-top:4px;
                border:1px solid #d1d5db; border-radius:6px; font-size:14px; }
  .auth button { width:100%; }
  .switch { font-size:13px; margin-top:14px; text-align:center; }
  a.btn-google { display:flex; align-items:center; justify-content:center; gap:8px;
                 background:#fff; color:#1f2933; border:1px solid #d1d5db;
                 padding:9px 16px; border-radius:6px; text-decoration:none; font-size:14px; }
  a.btn-google:hover { background:#f9fafb; }
  .domain-hint { font-size:12px; color:#9ca3af; text-align:center; margin-top:8px; }
  .lead { color:#4b5563; font-size:14px; margin-bottom:20px; }
</style>
</head>
<body>
<header class="topbar">
  <a href="{{ url_for('home') }}" class="brand">📁 ad-commファイル共有ツール</a>
  <nav>
    {% if session.uploader_email %}
      <span class="user">{{ session.uploader_email }} さん</span>
      <a href="{{ url_for('uploader_logout') }}">ログアウト</a>
    {% elif session.is_admin %}
      <span class="user">管理者</span>
      <a href="{{ url_for('admin_logout') }}">ログアウト</a>
    {% endif %}
  </nav>
</header>
<main>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="flash">{% for m in messages %}<div>{{ m }}</div>{% endfor %}</div>
    {% endif %}
  {% endwith %}
"""

PAGE_BOTTOM = """
</main>
</body>
</html>
"""


def layout(body):
    """共通の枠（ヘッダーなど）で本文をはさんで、1ページ分のHTMLにする"""
    return PAGE_TOP + body + PAGE_BOTTOM


GOOGLE_ICON_SVG = """<svg width="18" height="18" viewBox="0 0 48 48">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.3 35 24 35c-6.1 0-11-4.9-11-11s4.9-11 11-11c2.8 0 5.3 1 7.3 2.7l6-6C33.9 6.5 29.2 4.5 24 4.5 12.9 4.5 4 13.4 4 24.5s8.9 20 20 20 20-8.9 20-20c0-1.4-.1-2.7-.4-4z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 15.9 19 13 24 13c2.8 0 5.3 1 7.3 2.7l6-6C33.9 6.5 29.2 4.5 24 4.5c-7.8 0-14.5 4.4-17.7 10.2z"/>
      <path fill="#4CAF50" d="M24 44.5c5.2 0 9.9-1.7 13.4-4.7l-6.2-5.2c-2 1.4-4.6 2.2-7.2 2.2-5.3 0-9.7-3.4-11.3-8.1l-6.5 5C9.5 39.9 16.2 44.5 24 44.5z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4.1 5.4l6.2 5.2C40.9 36.1 44 30.8 44 24.5c0-1.4-.1-2.7-.4-4z"/>
    </svg>"""


# ---- 各画面の本文 ----------------------------------------------------------
HOME_BODY = """
<div class="card">
  <h2>ファイルをダウンロードする</h2>
  <p class="lead">共有されたファイル名とID/パスワードを入力してください。アカウント登録は不要です。</p>
  <form method="post" action="{{ url_for('download_lookup') }}" class="auth" style="margin:0;">
    <label>ダウンロードID<input type="text" name="download_id" required autofocus></label>
    <label>パスワード<input type="password" name="password" required></label>
    <button type="submit">ファイルを確認する</button>
  </form>
</div>

<div class="card">
  <h2>ファイルをアップロードする</h2>
  <p class="lead">アップロードには {{ allowed_domain }} のGoogleアカウントでのログインが必要です。</p>
  {% if session.uploader_email %}
    <a class="btn-download" href="{{ url_for('upload_page') }}">アップロード画面へ</a>
  {% else %}
    <a class="btn-google" href="{{ url_for('uploader_login') }}">
      """ + GOOGLE_ICON_SVG + """
      {{ allowed_domain }} のGoogleアカウントでログイン
    </a>
    <p class="domain-hint">※ @{{ allowed_domain }} のメールアドレスのみログインできます</p>
  {% endif %}
</div>
"""

UPLOAD_BODY = """
<div class="card">
  <h2>ファイルをアップロード</h2>
  <p class="hint">アップロード時に、ダウンロード用のID/パスワードを自分で決めてください。
  ダウンロードしたい相手にそのIDとパスワード、そしてこのサイトのURLを伝えてください。</p>
  <form method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data" class="upload-form">
    <label>ファイル<input type="file" name="file" required></label>
    <label>ダウンロードID（半角英数字。相手に伝える名前）<input type="text" name="download_id" required placeholder="例: sales-report-2026"></label>
    <label>ダウンロード用パスワード<input type="text" name="download_password" required placeholder="相手に伝えるパスワード"></label>
    <button type="submit">アップロードする</button>
  </form>
</div>

<div class="card">
  <h2>あなたがアップロードしたファイル</h2>
  {% if files %}
  <table>
    <thead>
      <tr><th>ファイル名</th><th>ダウンロードID</th><th>サイズ</th><th>日時</th><th></th></tr>
    </thead>
    <tbody>
      {% for f in files %}
      <tr>
        <td>{{ f.original_name }}</td>
        <td>{{ f.download_id }}</td>
        <td>{{ f.size | filesize }}</td>
        <td>{{ f.uploaded_at }}</td>
        <td class="actions">
          <form method="post" action="{{ url_for('delete', file_id=f.id) }}"
                onsubmit="return confirm('このファイルを削除しますか？');" style="display:inline">
            <button class="btn-delete" type="submit">削除</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">まだファイルがありません。</p>
  {% endif %}
</div>
"""

DOWNLOAD_RESULT_BODY = """
<div class="card">
  <h2>ファイルが見つかりました</h2>
  <table>
    <tr><th>ファイル名</th><td>{{ file.original_name }}</td></tr>
    <tr><th>サイズ</th><td>{{ file.size | filesize }}</td></tr>
    <tr><th>アップロード日時</th><td>{{ file.uploaded_at }}</td></tr>
  </table>
  <div style="margin-top:16px;">
    <a class="btn-download" href="{{ url_for('download', file_id=file.id, token=token) }}">ダウンロードする</a>
  </div>
</div>
"""

ADMIN_LOGIN_BODY = """
<div class="card auth">
  <h2>管理画面ログイン</h2>
  <form method="post">
    <label>ID<input type="text" name="username" required autofocus></label>
    <label>パスワード<input type="password" name="password" required></label>
    <button type="submit">ログイン</button>
  </form>
</div>
"""

ADMIN_BODY = """
<div class="card">
  <h2>アップロードされた全ファイル</h2>
  {% if files %}
  <table>
    <thead>
      <tr><th>ファイル名</th><th>ダウンロードID</th><th>サイズ</th><th>アップロード者</th><th>日時</th></tr>
    </thead>
    <tbody>
      {% for f in files %}
      <tr>
        <td>{{ f.original_name }}</td>
        <td>{{ f.download_id }}</td>
        <td>{{ f.size | filesize }}</td>
        <td>{{ f.uploader_email }}</td>
        <td>{{ f.uploaded_at }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="empty">まだファイルがありません。</p>
  {% endif %}
</div>
"""


# ---- トップページ ----------------------------------------------------------
@app.route("/")
def home():
    return render_template_string(layout(HOME_BODY), allowed_domain=ALLOWED_GOOGLE_DOMAIN)


# ---- アップロードする人のGoogleログイン ------------------------------------
@app.route("/auth/google")
def uploader_login():
    """アップロードするためのGoogleログインを開始する（ad-comm.com のみ許可）"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Googleログインは現在利用できません。管理者にお問い合わせください。")
        return redirect(url_for("home"))

    google = OAuth2Session(
        GOOGLE_CLIENT_ID,
        redirect_uri=GOOGLE_REDIRECT_URI,
        scope=["openid", "email", "profile"],
    )
    authorization_url, state = google.authorization_url(
        GOOGLE_AUTH_URL,
        access_type="offline",
        prompt="select_account",
        hd=ALLOWED_GOOGLE_DOMAIN,  # Google側にもドメインのヒントを渡す（最終判定はサーバー側）
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@app.route("/auth/google/callback")
def uploader_login_callback():
    """Googleからのコールバックを受け取り、ドメインを確認してログインさせる"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        flash("Googleログインは現在利用できません。管理者にお問い合わせください。")
        return redirect(url_for("home"))

    if request.args.get("error"):
        flash("Googleログインがキャンセルされました。")
        return redirect(url_for("home"))

    try:
        google = OAuth2Session(
            GOOGLE_CLIENT_ID,
            redirect_uri=GOOGLE_REDIRECT_URI,
            state=session.get("oauth_state"),
        )
        google.fetch_token(
            GOOGLE_TOKEN_URL,
            client_secret=GOOGLE_CLIENT_SECRET,
            authorization_response=request.url,
        )
        userinfo = google.get(GOOGLE_USERINFO_URL).json()
    except Exception:
        flash("Google認証に失敗しました。もう一度お試しください。")
        return redirect(url_for("home"))

    email = userinfo.get("email", "")
    email_verified = userinfo.get("email_verified", False)

    if not email or not email_verified:
        flash("Googleアカウントのメールアドレスが確認できませんでした。")
        return redirect(url_for("home"))

    # ---- ここでドメインを厳格にチェックする（最終判定はサーバー側） ----
    domain = email.split("@")[-1].lower()
    if domain != ALLOWED_GOOGLE_DOMAIN.lower():
        flash(f"@{ALLOWED_GOOGLE_DOMAIN} のGoogleアカウントのみアップロードできます。")
        return redirect(url_for("home"))

    session["uploader_email"] = email
    flash("ログインしました。")
    return redirect(url_for("upload_page"))


@app.route("/auth/logout")
def uploader_logout():
    session.pop("uploader_email", None)
    return redirect(url_for("home"))


# ---- アップロード画面 -------------------------------------------------------
@app.route("/upload")
@uploader_required
def upload_page():
    conn = get_db()
    files = conn.execute(
        "SELECT * FROM files WHERE uploader_email = ? ORDER BY id DESC",
        (session["uploader_email"],),
    ).fetchall()
    conn.close()
    return render_template_string(layout(UPLOAD_BODY), files=files)


@app.route("/upload", methods=["POST"])
@uploader_required
def upload():
    file = request.files.get("file")
    download_id = request.form.get("download_id", "").strip()
    download_password = request.form.get("download_password", "")

    if not file or file.filename == "":
        flash("ファイルが選択されていません。")
        return redirect(url_for("upload_page"))
    if not download_id or not download_password:
        flash("ダウンロードIDとパスワードを入力してください。")
        return redirect(url_for("upload_page"))

    conn = get_db()
    exists = conn.execute("SELECT 1 FROM files WHERE download_id = ?", (download_id,)).fetchone()
    if exists:
        conn.close()
        flash("そのダウンロードIDは既に使われています。別のIDにしてください。")
        return redirect(url_for("upload_page"))

    original_name = file.filename
    safe = secure_filename(original_name)  # 危険な文字を取り除く
    if safe == "":                         # 日本語だけの名前などで空になった場合の保険
        safe = "file"
    stored_name = f"{uuid.uuid4().hex}_{safe}"  # 実際にディスクへ保存する名前（重複防止）

    path = os.path.join(UPLOAD_DIR, stored_name)
    file.save(path)
    size = os.path.getsize(path)

    conn.execute(
        "INSERT INTO files (stored_name, original_name, uploader_email, download_id, "
        "password_hash, uploaded_at, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (stored_name, original_name, session["uploader_email"], download_id,
         generate_password_hash(download_password),
         datetime.now().strftime("%Y-%m-%d %H:%M"), size),
    )
    conn.commit()
    conn.close()
    flash("アップロードしました。相手にダウンロードIDとパスワードを伝えてください。")
    return redirect(url_for("upload_page"))


@app.route("/delete/<int:file_id>", methods=["POST"])
@uploader_required
def delete(file_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        conn.close()
        abort(404)
    if row["uploader_email"] != session["uploader_email"]:  # 自分のファイル以外は削除させない
        conn.close()
        abort(403)
    try:
        os.remove(os.path.join(UPLOAD_DIR, row["stored_name"]))
    except FileNotFoundError:
        pass
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()
    flash("削除しました。")
    return redirect(url_for("upload_page"))


# ---- ダウンロード（アカウント不要、ファイルごとのID/パスワードのみ） --------
@app.route("/download-lookup", methods=["POST"])
def download_lookup():
    download_id = request.form.get("download_id", "").strip()
    password = request.form.get("password", "")

    if not download_id or not password:
        flash("ダウンロードIDとパスワードを入力してください。")
        return redirect(url_for("home"))

    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE download_id = ?", (download_id,)).fetchone()
    conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        flash("ダウンロードIDまたはパスワードが違います。")
        return redirect(url_for("home"))

    # ダウンロードURLを推測されないよう、確認済みの合言葉としてセッションに一時保存する
    session[f"download_ok_{row['id']}"] = True
    return render_template_string(
        layout(DOWNLOAD_RESULT_BODY), file=row, token=row["id"]
    )


@app.route("/download/<int:file_id>")
def download(file_id):
    # 直前に download-lookup でパスワード確認が済んでいる場合のみ許可する
    if not session.get(f"download_ok_{file_id}"):
        flash("先にダウンロードIDとパスワードを入力してください。")
        return redirect(url_for("home"))

    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if row is None:
        abort(404)

    return send_from_directory(
        UPLOAD_DIR, row["stored_name"],
        as_attachment=True, download_name=row["original_name"],
    )


# ---- 管理画面（全ファイルの一覧のみ。ID/パスワードでログイン） --------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("IDまたはパスワードが違います。")
        return redirect(url_for("admin_login"))

    return render_template_string(layout(ADMIN_LOGIN_BODY))


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    files = conn.execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    conn.close()
    return render_template_string(layout(ADMIN_BODY), files=files)


@app.errorhandler(413)
def too_large(e):
    body = "<div class='card'><p>ファイルが大きすぎます（最大1GBまで）。</p>" \
           "<a href='/'>トップへ戻る</a></div>"
    return render_template_string(layout(body)), 413


# ---- アプリ起動 ------------------------------------------------------------
if __name__ == "__main__":
    # host="0.0.0.0" = 外部（tools.ad-comm.com など）からアクセスできる状態
    # debug=False    = 本番公開のため、Flaskのデバッグモードは無効化しています
    app.run(host="0.0.0.0", port=PORT, debug=False)
