"""One publishing run: build today's article, attach a photo, commit, push."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config


def load_daily_blog():
    """Import scripts/daily_blog.py from the mounted repository."""
    path = config.SITE_ROOT / "scripts" / "daily_blog.py"
    spec = importlib.util.spec_from_file_location("daily_blog", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def today_jst() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()


def attach_photo(date: str) -> bool:
    """Give the day's article a hero photo. Returns True if posts.json changed."""
    if not config.drive_configured():
        print(f"[PHOTO] skipped: {config.drive_status()}")
        return False
    data = json.loads(config.POSTS_FILE.read_text(encoding="utf-8"))
    posts = data.get("posts", [])
    target = next((p for p in posts if p.get("date") == date), None)
    if target is None:
        print(f"[PHOTO] no article dated {date}")
        return False
    if target.get("hero"):
        print(f"[PHOTO] {target['id']} already has a hero photo")
        return False
    try:
        from . import drive_photos
        hero = drive_photos.fetch_photo_for(date)
    except Exception as error:  # a Drive outage must not stop the text article
        print(f"[PHOTO] Drive failed, publishing without a photo: {error}")
        return False
    if not hero:
        return False
    target["hero"] = hero
    config.POSTS_FILE.write_text(
        json.dumps({"posts": posts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(config.SITE_ROOT), *args],
        check=True, capture_output=True, text=True,
    )


def commit_and_push(date: str) -> None:
    if not config.GIT_PUSH:
        print("[GIT] GIT_PUSH is off; changes are left in the working tree")
        return
    git("config", "user.name", config.GIT_AUTHOR_NAME)
    git("config", "user.email", config.GIT_AUTHOR_EMAIL)
    git("add", "data", "blog", "sitemap.xml", "assets")
    staged = subprocess.run(
        ["git", "-C", str(config.SITE_ROOT), "diff", "--cached", "--quiet"]
    )
    if staged.returncode == 0:
        print("[GIT] nothing new to publish today")
        return
    git("commit", "-m", f"content: publish BLUE COURT daily journal {date}")
    git("push", config.GIT_REMOTE, f"HEAD:{config.GIT_BRANCH}")
    print(f"[GIT] pushed to {config.GIT_REMOTE}/{config.GIT_BRANCH}")


def publish_once() -> str:
    date = today_jst()
    print(f"[RUN] BLUE COURT publish for {date} (JST)")
    daily_blog = load_daily_blog()
    daily_blog.generate()          # create today's article if missing
    if attach_photo(date):
        daily_blog.generate()      # rebuild pages so the photo is rendered
    commit_and_push(date)
    return date
