"""Draft once a day at PUBLISH_AT, Japan time (publishing is the admin's button).

wp-ai-bot's scheduler sleeps a fixed number of hours, which drifts away from
the intended posting time after a restart. This one aims at a JST wall clock
instead, so a restart at any hour still posts at the same local time.
"""
from __future__ import annotations

import time
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .drafts import create_today

JST = ZoneInfo("Asia/Tokyo")


def next_run(now: datetime) -> datetime:
    hour, minute = (int(part) for part in config.PUBLISH_AT.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def main() -> None:
    print(f"[SCHEDULER] daily draft at {config.PUBLISH_AT} JST (published only from the admin screen)")
    if config.RUN_AT_START:
        try:
            create_today()
        except Exception as error:
            print("[SCHEDULER] first run failed:", error)
            traceback.print_exc()
    while True:
        now = datetime.now(JST)
        target = next_run(now)
        print(f"[SCHEDULER] next run {target.isoformat()}")
        time.sleep(max(1, int((target - now).total_seconds())))
        try:
            create_today()
        except Exception as error:
            print("[SCHEDULER] run failed:", error)
            traceback.print_exc()
            time.sleep(60)


if __name__ == "__main__":
    main()
