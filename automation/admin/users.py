"""Manage admin accounts from the VPS shell (there is no sign-up screen on purpose).

    docker compose run --rm -it --entrypoint python admin -m automation.admin.users add <名前>
    docker compose run --rm -it --entrypoint python admin -m automation.admin.users passwd <名前>
    docker compose run --rm --entrypoint python admin -m automation.admin.users list
    docker compose run --rm --entrypoint python admin -m automation.admin.users remove <名前>

パスワードは画面に表示されない入力（getpass）で、本人が打つ。ここで生成はしない。
"""
from __future__ import annotations

import getpass
import sys

from . import auth


def ask_password() -> str:
    first = getpass.getpass(f"パスワード（{auth.MIN_PASSWORD}文字以上）: ")
    second = getpass.getpass("もう一度: ")
    if first != second:
        raise SystemExit("一致しませんでした。変更していません")
    return first


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("add", "passwd", "list", "remove"):
        print(__doc__)
        return 2
    command, *rest = argv
    if command == "list":
        for name, entry in sorted(auth.load_users().items()):
            print(name, entry.get("createdAt", ""))
        return 0
    if len(rest) != 1:
        print("名前を1つ指定してください")
        return 2
    name = rest[0]
    exists = name in auth.load_users()
    if command == "add" and exists:
        print(f"{name} はすでにあります。パスワードを変えるなら passwd を使ってください")
        return 1
    if command == "passwd" and not exists:
        print(f"{name} はありません")
        return 1
    if command == "remove":
        print("削除しました" if auth.remove_user(name) else f"{name} はありません")
        return 0
    try:
        auth.set_password(name, ask_password())
    except ValueError as error:
        print(error)
        return 1
    print(f"{name} を{'追加' if command == 'add' else '更新'}しました（既存のログインは無効になります）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
