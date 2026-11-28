"""BLUE COURT admin screen: log in, check the daily draft, press 公開.

Served by gunicorn on 127.0.0.1:${ADMIN_PORT}; nginx forwards https://yscc.joeai.co.jp/admin/
to it. Every route lives under /admin/ so nginx needs a single location.
設計と理由は docs/admin.md。
"""
from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for)
from markupsafe import escape
from werkzeug.middleware.proxy_fix import ProxyFix

from automation.app import config, drafts, writer

from . import auth

PREFIX = "/admin"


def create_app(throttle: auth.Throttle | None = None) -> Flask:
    app = Flask(__name__, static_url_path=PREFIX + "/static")
    # nginx が X-Forwarded-For を $remote_addr で上書きして渡す（1段だけ信用する）。
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.config.update(
        SECRET_KEY=auth.session_secret(),
        SESSION_COOKIE_NAME="bc_admin",
        SESSION_COOKIE_PATH=PREFIX,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=config.ADMIN_COOKIE_SECURE,
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=256 * 1024,
    )
    limiter = throttle or auth.Throttle()

    # --- security plumbing --------------------------------------------------

    @app.after_request
    def headers(response: Response) -> Response:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        # JS は使わない。プレビューは記事ページの <style> を含むので style だけ inline を許す。
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    def csrf_token() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            sent = request.form.get("csrf", "")
            if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
                abort(400, "フォームの有効期限が切れました。ページを開き直してください")

    def current_user() -> str | None:
        name = session.get("user")
        if not name:
            return None
        # パスワード変更・アカウント削除で、それ以前のログインを無効にする。
        if auth.generation(name) != session.get("gen"):
            session.clear()
            return None
        return name

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            g.user = user
            return view(*args, **kwargs)
        return wrapped

    def client_ip() -> str:
        return request.remote_addr or "unknown"

    # --- login --------------------------------------------------------------

    @app.route(PREFIX + "/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            if current_user():
                return redirect(url_for("dashboard"))
            return render_template("login.html", error=None, no_users=not auth.load_users())
        name = request.form.get("username", "").strip()[:40]
        password = request.form.get("password", "")[:200]
        keys = ("ip:" + client_ip(), "user:" + name)
        if limiter.blocked(*keys):
            print(f"[ADMIN] login blocked (too many failures) user={name!r} ip={client_ip()}")
            return render_template("login.html", no_users=False,
                                   error="失敗が続いたため、しばらくログインできません。15分ほど待ってください"), 429
        entry = auth.verify(name, password)
        if entry is None:
            limiter.fail(*keys)
            print(f"[ADMIN] login failed user={name!r} ip={client_ip()}")
            return render_template("login.html", no_users=False,
                                   error="名前かパスワードが違います"), 401
        limiter.clear(*keys)
        session.clear()  # ログイン前のセッションを引き継がない
        session.permanent = True
        session["user"] = name
        session["gen"] = int(entry.get("generation", 0))
        print(f"[ADMIN] login ok user={name!r} ip={client_ip()}")
        return redirect(url_for("dashboard"))

    @app.post(PREFIX + "/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # --- dashboard ----------------------------------------------------------

    @app.get(PREFIX + "/")
    @login_required
    def dashboard():
        items = drafts.load()
        for item in items:
            item["problems"] = drafts.problems(item)
        posts = drafts.load_posts()
        today = drafts.publisher.today_jst()
        has_today = any(p.get("date") == today for p in posts) or any(d["date"] == today for d in items)
        return render_template("dashboard.html", drafts=items, posts=posts[:40], today=today,
                               has_today=has_today, base=base_url())

    @app.get(PREFIX)
    def root():
        return redirect(url_for("dashboard"))

    @app.post(PREFIX + "/drafts/new")
    @login_required
    def new_draft():
        created = drafts.create_today()
        if created:
            flash(f"今日の下書きを作りました（{created['note']}）", "ok")
            return redirect(url_for("draft", draft_id=created["id"]))
        flash("今日の記事か下書きがすでにあります", "error")
        return redirect(url_for("dashboard"))

    @app.post(PREFIX + "/rebuild")
    @login_required
    def rebuild():
        with drafts.lock():
            result = drafts.publisher.rebuild_and_ship("content: rebuild BLUE COURT site")
        flash("公開サイトを書き出し直しました。" + result["git"], "ok" if result["pushed"] else "error")
        return redirect(url_for("dashboard"))

    # --- one draft ----------------------------------------------------------

    def load_draft(draft_id: str) -> dict:
        try:
            return drafts.get(draft_id)
        except drafts.DraftError:
            abort(404)

    @app.get(PREFIX + "/drafts/<draft_id>")
    @login_required
    def draft(draft_id):
        item = load_draft(draft_id)
        has_photo = bool(item.get("photo")) and drafts.photo_path(draft_id).exists()
        return render_template("draft.html", d=item, problems=drafts.problems(item),
                               categories=writer.EDIT_CATEGORIES, has_photo=has_photo,
                               body_text="\n\n".join(item.get("body", [])))

    @app.post(PREFIX + "/drafts/<draft_id>")
    @login_required
    def save_draft(draft_id):
        load_draft(draft_id)
        form = request.form
        body = [p for p in form.get("body", "").replace("\r\n", "\n").split("\n\n")]
        found = drafts.update(draft_id, form.get("category", ""), form.get("headline", ""),
                              form.get("summary", ""), body,
                              alt=form.get("alt"), credit=form.get("credit"))
        if form.get("action") != "publish":
            flash("保存しました（まだ公開していません）" if not found
                  else "保存しました。ただしこのままでは公開できません", "ok" if not found else "error")
            return redirect(url_for("draft", draft_id=draft_id))
        try:
            result = drafts.publish(draft_id)
        except drafts.DraftError as error:
            flash(str(error), "error")
            return redirect(url_for("draft", draft_id=draft_id))
        print(f"[ADMIN] published {draft_id} by {g.user!r}")
        flash("公開しました。" + result["git"], "ok" if result["pushed"] else "error")
        return redirect(url_for("dashboard"))

    @app.post(PREFIX + "/drafts/<draft_id>/regenerate")
    @login_required
    def regenerate(draft_id):
        load_draft(draft_id)
        try:
            title = drafts.regenerate(draft_id)
            flash(f"AIが書き直しました: {title}", "ok")
        except drafts.DraftError as error:
            flash(str(error), "error")
        return redirect(url_for("draft", draft_id=draft_id))

    @app.get(PREFIX + "/drafts/<draft_id>/preview")
    @login_required
    def preview(draft_id):
        item = load_draft(draft_id)
        post = drafts.to_post(item)
        marker = "assets/__draft_photo__"
        if item.get("photo") and drafts.photo_path(draft_id).exists():
            post["hero"] = {"src": marker, "alt": item["photo"].get("alt", ""),
                            "credit": item["photo"].get("credit", "")}
        html = drafts.publisher.load_daily_blog().page(post)
        photo_url = url_for("draft_photo", draft_id=draft_id)
        html = html.replace("../" + str(escape(marker)), photo_url)
        # 記事ページは /blog/ からの相対パスで CSS を読むので、基準を合わせる。
        html = html.replace("<head>", '<head><base href="/blog/">', 1)
        banner = ('<div style="background:var(--orange);color:var(--navy);font-weight:800;padding:10px 16px;'
                  'position:sticky;top:0;z-index:99">プレビュー（未公開）— この画面は公開サイトには出ていません</div>')
        html = html.replace("<body>", "<body>" + banner, 1)
        return Response(html, mimetype="text/html")

    @app.get(PREFIX + "/drafts/<draft_id>/photo")
    @login_required
    def draft_photo(draft_id):
        path = drafts.photo_path(draft_id)
        if not path.exists():
            abort(404)
        return send_file(path, mimetype="image/jpeg", max_age=0)

    @app.post(PREFIX + "/drafts/<draft_id>/photo/remove")
    @login_required
    def remove_photo(draft_id):
        load_draft(draft_id)
        drafts.remove_photo(draft_id)
        flash("写真を外しました", "ok")
        return redirect(url_for("draft", draft_id=draft_id))

    @app.get(PREFIX + "/drafts/<draft_id>/photos")
    @login_required
    def choose_photo(draft_id):
        item = load_draft(draft_id)
        if not config.drive_configured():
            flash(f"Google Drive が設定されていません（{config.drive_status()}）", "error")
            return redirect(url_for("draft", draft_id=draft_id))
        from automation.app import drive_photos
        try:
            images = drive_photos.folder_images()
        except Exception as error:
            images = None
            print(f"[ADMIN] Drive list failed: {error}")
        if images is None:
            flash("Google Drive のフォルダに届きませんでした", "error")
            return redirect(url_for("draft", draft_id=draft_id))
        used = {e["fileId"]: e for e in drive_photos.load_ledger().get("photos", [])}
        others = drafts.photo_on_drafts([d for d in drafts.load() if d["id"] != draft_id])
        return render_template("photos.html", d=item, images=images, used=used, others=others)

    @app.post(PREFIX + "/drafts/<draft_id>/photos")
    @login_required
    def set_photo(draft_id):
        load_draft(draft_id)
        try:
            drafts.set_photo(draft_id, request.form.get("file_id", ""),
                             request.form.get("name", "")[:200])
            flash("写真を差し替えました。代替テキストを写真に合わせて直してください", "ok")
        except drafts.DraftError as error:
            flash(str(error), "error")
        return redirect(url_for("draft", draft_id=draft_id))

    @app.get(PREFIX + "/drive/<file_id>/thumb")
    @login_required
    def thumb(file_id):
        if not drafts.ID_RE.match(file_id):
            abort(404)
        cache = config.ADMIN_DATA_DIR / "thumbs" / f"{file_id}.jpg"
        if not cache.exists():
            from automation.app import drive_photos
            try:
                data = drive_photos.thumbnail_jpeg(
                    drive_photos.download(drive_photos.build_service(), file_id))
            except Exception as error:
                print(f"[ADMIN] thumbnail failed for {file_id}: {type(error).__name__}")
                abort(404)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
        return send_file(cache, mimetype="image/jpeg", max_age=0)

    # --- unpublish ----------------------------------------------------------

    def load_post(post_id: str) -> dict:
        post = next((p for p in drafts.load_posts() if p["id"] == post_id), None)
        if post is None:
            abort(404)
        return post

    @app.get(PREFIX + "/posts/<post_id>/unpublish")
    @login_required
    def confirm_unpublish(post_id):
        return render_template("unpublish.html", post=load_post(post_id), base=base_url())

    @app.post(PREFIX + "/posts/<post_id>/unpublish")
    @login_required
    def unpublish(post_id):
        load_post(post_id)
        try:
            result = drafts.unpublish(post_id)
        except drafts.DraftError as error:
            flash(str(error), "error")
            return redirect(url_for("dashboard"))
        print(f"[ADMIN] unpublished {post_id} by {g.user!r}")
        flash("非公開にしました（下書きに戻しました）。" + result["git"], "ok" if result["pushed"] else "error")
        return redirect(url_for("dashboard"))

    @app.errorhandler(400)
    @app.errorhandler(404)
    def error_page(error):
        return render_template("error.html", error=error), error.code

    return app


def base_url() -> str:
    import os
    base = os.environ.get("SITE_BASE_URL", "https://yscc.joeai.co.jp/")
    return base if base.endswith("/") else base + "/"
