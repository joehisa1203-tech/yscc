#!/usr/bin/env python3
"""Check that the live site serves a recent article and no private file.

Why content and not HTTP 200: the old smoke test only looked for 'JFL 2026' on
the top page, so it stayed green while the site served a stale copy from another
repository. A green check that cannot fail is worse than no check.

Usage: python3 scripts/check_live_site.py [base-url]
Exit status 0 = the live site is current and leaks nothing.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = (sys.argv[1] if len(sys.argv) > 1 else
        os.environ.get("SITE_BASE_URL", "https://yscc.joeai.co.jp/")).rstrip("/") + "/"
PRIVATE = (".env", "secrets/google-service-account.json", "automation/app/config.py",
           "admin-data/drafts.json", "admin-data/users.json")
# 半自動（管理画面の公開ボタン）になったので、当日の記事が無い日は普通にある。
# 最新の記事がこの日数より古ければ「更新が止まっている」とみなして落とす。
FRESH_DAYS = int(os.environ.get("CHECK_FRESH_DAYS", "3"))
ATTEMPTS = int(os.environ.get("CHECK_ATTEMPTS", "10"))


def fetch(url: str, timeout: int = 25):
    request = urllib.request.Request(url, headers={"User-Agent": "blue-court-site-check"})
    return urllib.request.urlopen(request, timeout=timeout)


def today_jst() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()


def check_fresh() -> bool:
    today = today_jst()
    oldest_ok = (datetime.fromisoformat(today) - timedelta(days=FRESH_DAYS)).date().isoformat()
    for attempt in range(1, ATTEMPTS + 1):
        try:
            posts = json.loads(fetch(BASE + "data/posts.json").read())["posts"]
            latest = max(p["date"] for p in posts)
            print(f"live site: latest {latest}, {len(posts)} articles (today {today})")
            if latest >= oldest_ok:
                return True
        except (urllib.error.URLError, ValueError, KeyError) as error:
            print(f"attempt {attempt}/{ATTEMPTS}: {error}")
        if attempt < ATTEMPTS:
            time.sleep(30)
    print(f"FAIL: no article published since {oldest_ok}.")
    print("Check the drafts waiting in https://yscc.joeai.co.jp/admin/ (and: docker compose logs scheduler)")
    return False


def check_no_leak() -> bool:
    ok = True
    for path in PRIVATE:
        try:
            status = fetch(BASE + path, timeout=20).status
        except urllib.error.HTTPError as error:
            status = error.code
        except urllib.error.URLError as error:
            print(f"{path} -> could not be checked ({error})")
            continue
        print(f"{path} -> {status}")
        if status == 200:
            print("FAIL: a private file is published. Fix the web server first.")
            ok = False
    return ok


if __name__ == "__main__":
    fresh = check_fresh()
    clean = check_no_leak()
    sys.exit(0 if fresh and clean else 1)
