# -*- coding: utf-8 -*-
"""
ファイル共有ツール

できること：
  - 利用者ごとにアカウントを作成（新規登録／ログイン）
  - ログインした人だけがファイルをアップロード／ダウンロードできる
  - アップロードしたファイルは、ログインした全員で共有される
  - 自分がアップロードしたファイルは自分で削除できる

必要なもの：
  - Python 3.9 以上
  - Flask, python-dotenv（pip install -r requirements.txt でインストール）

起動設定（.env で変更可能。詳しくは .env.example を参照）：
  - PORT           : 待ち受けポート（デフォルト 8082）
  - SECRET_KEY     : セッション暗号化キー（公開前に必ず変更してください）
  - ADMIN_USERNAME : 管理者ログインID（デフォルト admin）
  - ADMIN_PASSWORD : 管理者初期パスワード（公開前に必ず変更してください）
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

load_dotenv()  # 同じフォルダの .env を読み込む

# ---- 基本設定 --------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")    # 実ファイルの保存先フォルダ
DB_PATH = os.path.join(BASE_DIR, "database.db")   # ユーザー・ファイル情報のデータベース
MAX_CONTENT_LENGTH = 1024 * 1024 * 1024           # 1ファイルの上限（1GB）

PORT = int(os.environ.get("PORT", 8082))

# 管理者アカウント（管理画面で全アカウント・全ファイルを閲覧できます）
# ※ .env の ADMIN_USERNAME / ADMIN_PASSWORD で上書きできます。公開前に必ず変更してください。
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")

os.makedirs(UPLOAD_DIR, exist_ok=True)            # uploads フォルダが無ければ自動作成

app = Flask(__name__)
# ↓ ログイン状態（セッション）を暗号化する鍵。.env の SECRET_KEY で上書きできます。公開前に必ず変更してください。
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
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,   -- ログインID
            password_hash TEXT NOT NULL,          -- 暗号化したパスワード
            is_admin      INTEGER NOT NULL DEFAULT 0  -- 1なら管理者
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            stored_name   TEXT NOT NULL,   -- 保存時の実ファイル名（重複防止のためUUID付き）
            original_name TEXT NOT NULL,   -- 元のファイル名（表示・DL用）
            uploader      TEXT NOT NULL,   -- アップロードした人のID
            uploaded_at   TEXT NOT NULL,   -- アップロード日時
            size          INTEGER NOT NULL -- ファイルサイズ（バイト）
        )
    """)

    # 以前のバージョンで作ったデータベースに is_admin 列が無ければ追加する
    columns = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    # 管理者アカウントがまだ無ければ作成する
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if exists is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD)),
        )

    conn.commit()
    conn.close()


init_db()


# ---- ログインしていないと使えないようにする仕組み --------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """管理者だけが使える画面のための制限"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            abort(403)  # 一般ユーザーは管理画面に入れない
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
<title>ad-comm ファイル共有ツール</title>
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
  .badge-admin { background:#2563eb; color:#fff; padding:2px 8px; border-radius:6px; font-size:12px; }
  button { background:#2563eb; color:#fff; border:none; padding:9px 16px;
           border-radius:6px; cursor:pointer; font-size:14px; }
  .upload-form { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .hint, .empty { color:#6b7280; font-size:13px; }
  .auth { max-width:360px; margin:0 auto; }
  .auth label { display:block; margin-bottom:12px; font-size:14px; }
  .auth input { display:block; width:100%; padding:9px; margin-top:4px;
                border:1px solid #d1d5db; border-radius:6px; font-size:14px; }
  .auth button { width:100%; }
  .switch { font-size:13px; margin-top:14px; text-align:center; }
</style>
</head>
<body>
<header class="topbar">
  <a href="{{ url_for('index') }}" class="brand">📁 ファイル共有ツール</a>
  <nav>
    {% if session.username %}
      {% if session.is_admin %}<a href="{{ url_for('admin') }}">管理画面</a>{% endif %}
      <span class="user">{{ session.username }} さん</span>
      <a href="{{ url_for('logout') }}">ログアウト</a>
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


# ---- 各画面の本文 ----------------------------------------------------------
INDEX_BODY = """
<div class="card">
  <h2>ファイルをアップロード</h2>
  <form method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data" class="upload-form">
    <input type="file" name="file" required>
    <button type="submit">アップロード</button>
  </form>
  <p class="hint">※ 1ファイル最大1GBまで</p>
</div>

<div class="card">
  <h2>アップロードしたファイル</h2>
  <p class="hint">アップロードしたファイルは、あなただけが見られます。</p>
  {% if files %}
  <table>
    <thead>
      <tr><th>ファイル名</th><th>サイズ</th><th>日時</th><th></th></tr>
    </thead>
    <tbody>
      {% for f in files %}
      <tr>
        <td>{{ f.original_name }}</td>
        <td>{{ f.size | filesize }}</td>
        <td>{{ f.uploaded_at }}</td>
        <td class="actions">
          <a class="btn-download" href="{{ url_for('download', file_id=f.id) }}">ダウンロード</a>
          {% if f.uploader == session.username %}
          <form method="post" action="{{ url_for('delete', file_id=f.id) }}"
                onsubmit="return confirm('このファイルを削除しますか？');" style="display:inline">
            <button class="btn-delete" type="submit">削除</button>
          </form>
          {% endif %}
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

LOGIN_BODY = """
<div class="card auth">
  <h2>ログイン</h2>
  <form method="post">
    <label>ID<input type="text" name="username" required autofocus></label>
    <label>パスワード<input type="password" name="password" required></label>
    <button type="submit">ログイン</button>
  </form>
  <p class="switch">アカウントがない方は <a href="{{ url_for('register') }}">新規登録</a></p>
</div>
"""

REGISTER_BODY = """
<div class="card auth">
  <h2>新規登録</h2>
  <form method="post">
    <label>ID<input type="text" name="username" required autofocus></label>
    <label>パスワード<input type="password" name="password" required></label>
    <button type="submit">登録する</button>
  </form>
  <p class="switch">すでにアカウントをお持ちの方は <a href="{{ url_for('login') }}">ログイン</a></p>
</div>
"""

ADMIN_BODY = """
<div class="card">
  <h2>アカウント一覧</h2>
  <table>
    <thead>
      <tr><th>ID（ユーザー名）</th><th>権限</th><th>ファイル数</th></tr>
    </thead>
    <tbody>
      {% for u in users %}
      <tr>
        <td>{{ u.username }}</td>
        <td>{% if u.is_admin %}<span class="badge-admin">管理者</span>{% else %}一般{% endif %}</td>
        <td>{{ counts.get(u.username, 0) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="card">
  <h2>アップロードされた全ファイル</h2>
  {% if files %}
  <table>
    <thead>
      <tr><th>ファイル名</th><th>サイズ</th><th>アップロード者</th><th>日時</th><th></th></tr>
    </thead>
    <tbody>
      {% for f in files %}
      <tr>
        <td>{{ f.original_name }}</td>
        <td>{{ f.size | filesize }}</td>
        <td>{{ f.uploader }}</td>
        <td>{{ f.uploaded_at }}</td>
        <td class="actions">
          <a class="btn-download" href="{{ url_for('download', file_id=f.id) }}">ダウンロード</a>
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


# ---- 画面ごとの処理（ルート） ----------------------------------------------
@app.route("/")
@login_required
def index():
    conn = get_db()
    files = conn.execute(
        "SELECT * FROM files WHERE uploader = ? ORDER BY id DESC",
        (session["username"],),
    ).fetchall()
    conn.close()
    return render_template_string(layout(INDEX_BODY), files=files)


@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    files = conn.execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    conn.close()
    # 各ユーザーのアップロード数を数える
    counts = {}
    for f in files:
        counts[f["uploader"]] = counts.get(f["uploader"], 0) + 1
    return render_template_string(layout(ADMIN_BODY), users=users, files=files, counts=counts)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("IDとパスワードを入力してください。")
            return redirect(url_for("register"))
        conn = get_db()
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            conn.close()
            flash("そのIDは既に使われています。別のIDにしてください。")
            return redirect(url_for("register"))
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
        conn.close()
        flash("登録しました。ログインしてください。")
        return redirect(url_for("login"))
    return render_template_string(layout(REGISTER_BODY))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session["username"] = username
            session["is_admin"] = bool(row["is_admin"])
            return redirect(url_for("index"))
        flash("IDまたはパスワードが違います。")
        return redirect(url_for("login"))
    return render_template_string(layout(LOGIN_BODY))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("ファイルが選択されていません。")
        return redirect(url_for("index"))

    original_name = file.filename
    safe = secure_filename(original_name)  # 危険な文字を取り除く
    if safe == "":                         # 日本語だけの名前などで空になった場合の保険
        safe = "file"
    stored_name = f"{uuid.uuid4().hex}_{safe}"  # 実際にディスクへ保存する名前（重複防止）

    path = os.path.join(UPLOAD_DIR, stored_name)
    file.save(path)
    size = os.path.getsize(path)

    conn = get_db()
    conn.execute(
        "INSERT INTO files (stored_name, original_name, uploader, uploaded_at, size) "
        "VALUES (?, ?, ?, ?, ?)",
        (stored_name, original_name, session["username"],
         datetime.now().strftime("%Y-%m-%d %H:%M"), size),
    )
    conn.commit()
    conn.close()
    flash("アップロードしました。")
    return redirect(url_for("index"))


@app.route("/download/<int:file_id>")
@login_required
def download(file_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if row is None:
        abort(404)
    # 自分のファイル、または管理者だけがダウンロードできる
    if row["uploader"] != session["username"] and not session.get("is_admin"):
        abort(403)
    # 元のファイル名でダウンロードさせる（日本語名もそのまま）
    return send_from_directory(
        UPLOAD_DIR, row["stored_name"],
        as_attachment=True, download_name=row["original_name"],
    )


@app.route("/delete/<int:file_id>", methods=["POST"])
@login_required
def delete(file_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        conn.close()
        abort(404)
    if row["uploader"] != session["username"]:  # 自分のファイル以外は削除させない
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
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(e):
    body = "<div class='card'><p>ファイルが大きすぎます（最大1GBまで）。</p>" \
           "<a href='/'>一覧へ戻る</a></div>"
    return render_template_string(layout(body)), 413


# ---- アプリ起動 ------------------------------------------------------------
if __name__ == "__main__":
    # host="0.0.0.0" = 外部（tools.ad-comm.com など）からアクセスできる状態
    # debug=False    = 本番公開のため、Flaskのデバッグモードは無効化しています
    app.run(host="0.0.0.0", port=PORT, debug=False)
