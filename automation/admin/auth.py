"""Admin accounts, password checks and login throttling.

- パスワードは平文で持たない。werkzeug の scrypt ハッシュだけを admin-data/users.json に置く。
- アカウントは画面からは作れない。VPS上で `python -m automation.admin.users add <名前>` を
  実行し、**本人がパスワードを入力する**（こちらで決めたり代わりに入力したりしない）。
- 同じIP・同じ名前で失敗が続いたら一定時間ログインを受け付けない。公開URLに置く
  ログイン画面は総当たりの的になるため。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from automation.app import config

MIN_PASSWORD = 12
MAX_FAILURES = 5          # この回数失敗したら
WINDOW_SECONDS = 15 * 60  # この時間ログインを止める
NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
# 存在しない名前でも同じだけ時間をかける（名前の有無を応答時間から当てさせない）。
_DUMMY_HASH = generate_password_hash("not-a-real-password-for-timing")


def users_file() -> Path:
    return config.ADMIN_DATA_DIR / "users.json"


def load_users() -> dict:
    path = users_file()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("users", {})


def save_users(users: dict) -> None:
    path = users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def valid_name(name: str) -> bool:
    return 1 <= len(name) <= 40 and set(name) <= NAME_CHARS


def set_password(name: str, password: str) -> None:
    if not valid_name(name):
        raise ValueError("名前は英数字と _ - . で40文字以内にしてください")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"パスワードは{MIN_PASSWORD}文字以上にしてください")
    users = load_users()
    entry = users.get(name, {"createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
    entry["hash"] = generate_password_hash(password)
    # パスワードを変えたら、その人の既存のログイン（セッション）を無効にするための番号。
    entry["generation"] = int(entry.get("generation", 0)) + 1
    users[name] = entry
    save_users(users)


def remove_user(name: str) -> bool:
    users = load_users()
    if name not in users:
        return False
    del users[name]
    save_users(users)
    return True


def verify(name: str, password: str) -> dict | None:
    """Return the user entry when name/password match, else None."""
    entry = load_users().get(name)
    if entry is None:
        check_password_hash(_DUMMY_HASH, password)
        return None
    return entry if check_password_hash(entry["hash"], password) else None


def generation(name: str) -> int | None:
    entry = load_users().get(name)
    return None if entry is None else int(entry.get("generation", 0))


class Throttle:
    """In-memory failure counter. gunicorn は1プロセスで動かすので、メモリで足りる。"""

    def __init__(self, limit: int = MAX_FAILURES, window: int = WINDOW_SECONDS):
        self.limit, self.window = limit, window
        self.failures: dict[str, deque] = defaultdict(deque)
        self.mutex = threading.Lock()

    def _trim(self, key: str, now: float) -> deque:
        bucket = self.failures[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        return bucket

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self.mutex:
            return any(len(self._trim(key, now)) >= self.limit for key in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self.mutex:
            for key in keys:
                self._trim(key, now).append(now)

    def clear(self, *keys: str) -> None:
        with self.mutex:
            for key in keys:
                self.failures.pop(key, None)


def session_secret() -> bytes:
    """Cookie の署名鍵。初回にアプリが乱数で作り admin-data/session.key（600）に置く。

    値は画面にもログにも出さない。消すと全員ログアウトされるだけで、復旧の必要はない。
    """
    path = config.ADMIN_DATA_DIR / "session.key"
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return key
