"""Building and shipping the public site: page rebuild, export to nginx, git push.

半自動化（2026-11-28）以降、ここは「公開された記事をサイトに出す」部品だけを持つ。
記事を下書きとして用意する・公開ボタンで posts.json に入れるのは drafts.py。
**posts.json に入っているものが公開中の記事**で、下書きはここを通らない。
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

# daily_blog.py はこのコードと同じリポジトリから読む。パス（SITE/POSTS/ARTICLES）は
# config から上書きする。ファイル位置から決まる既定値のままだと、config を差し替えた
# テストでも本物の data/ と blog/ を書き換えてしまう。
CODE_ROOT = Path(__file__).resolve().parents[2]


def load_daily_blog():
    """Import scripts/daily_blog.py, pointed at config.SITE_ROOT."""
    path = CODE_ROOT / "scripts" / "daily_blog.py"
    spec = importlib.util.spec_from_file_location("daily_blog", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SITE = config.SITE_ROOT
    module.POSTS = config.POSTS_FILE
    module.ARTICLES = config.SITE_ROOT / "blog"
    return module


def today_jst() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()


# 公開してよいものだけを書き出す。リポジトリをそのまま配ると
# https://.../.env でAPIキーとDrive設定が読めてしまう。拒否リストではなく
# 許可リストにしているのは、新しいファイルが増えたときに漏れないようにするため。
# admin-data/（下書き・管理者のパスワードハッシュ）はここに入れない。
PUBLIC_FILES = ("index.html", "app.js", "styles.css", "football.css",
                "favicon.svg", "robots.txt", "sitemap.xml", ".nojekyll")
PUBLIC_DIRS = ("blog", "data", "assets")


def export_site() -> Path:
    """Copy the public subset into SITE_EXPORT_DIR and return that directory."""
    target = config.SITE_EXPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        source = config.SITE_ROOT / name
        if source.exists():
            shutil.copyfile(source, target / name)
    for name in PUBLIC_DIRS:
        source = config.SITE_ROOT / name
        if not source.is_dir():
            continue
        destination = target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    print(f"[SITE] exported {target}")
    return target


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(config.SITE_ROOT), *args],
        check=True, capture_output=True, text=True,
    )


def commit_and_push(message: str) -> str:
    """Commit the public content and push. Returns a one-line result for the log/UI.

    Raises subprocess.CalledProcessError when the push fails: the caller shows it,
    because the site is already updated and only GitHub is behind.
    """
    if not config.GIT_PUSH:
        print("[GIT] GIT_PUSH is off; changes are left in the working tree")
        return "GIT_PUSH が 0 のため、GitHub には送っていません"
    git("config", "user.name", config.GIT_AUTHOR_NAME)
    git("config", "user.email", config.GIT_AUTHOR_EMAIL)
    # ディレクトリ指定の add は削除も拾う（非公開にした記事のページが消える）。
    git("add", "data", "blog", "sitemap.xml", "robots.txt", "assets")
    staged = subprocess.run(
        ["git", "-C", str(config.SITE_ROOT), "diff", "--cached", "--quiet"]
    )
    if staged.returncode == 0:
        print("[GIT] nothing new to publish")
        return "変更が無いため、コミットしていません"
    git("commit", "-m", message)
    git("push", config.GIT_REMOTE, f"HEAD:{config.GIT_BRANCH}")
    print(f"[GIT] pushed to {config.GIT_REMOTE}/{config.GIT_BRANCH}")
    return f"GitHub（{config.GIT_REMOTE}/{config.GIT_BRANCH}）へ送りました"


def rebuild_and_ship(message: str) -> dict:
    """posts.json からページを作り直し、公開ディレクトリへ出し、push する。

    公開サイトの更新と GitHub への push は別の結果として返す。push が失敗しても
    サイトはもう更新されているので、それを「公開失敗」と表示しないため。
    """
    load_daily_blog().build()
    export_site()
    try:
        return {"pushed": True, "git": commit_and_push(message)}
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip().splitlines()
        print("[GIT] failed:", detail[-1:] if detail else error)
        return {"pushed": False, "git": "GitHubへの送信に失敗しました: " + (detail[-1] if detail else str(error))}
