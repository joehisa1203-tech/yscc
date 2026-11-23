"""Environment configuration for the BLUE COURT blog automation container.

Every Drive/git related setting is optional on purpose: with nothing configured
the app still publishes the daily text article, so a missing credential can
never stop the blog. See docs/automation.md for the full table.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repository root. The container bind-mounts the repository at /app.
SITE_ROOT = Path(os.environ.get("SITE_ROOT", Path(__file__).resolve().parents[2]))

DATA_DIR = SITE_ROOT / "data"
POSTS_FILE = DATA_DIR / "posts.json"
PHOTO_LEDGER = DATA_DIR / "photos.json"
PHOTO_DIR = SITE_ROOT / "assets" / "photos"
PHOTO_WEB_DIR = "assets/photos"

# --- Google Drive -----------------------------------------------------------
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

# --- Photo rendering --------------------------------------------------------
PHOTO_WIDTH = int(os.environ.get("PHOTO_WIDTH", "1600"))
PHOTO_HEIGHT = int(os.environ.get("PHOTO_HEIGHT", "900"))
PHOTO_QUALITY = int(os.environ.get("PHOTO_QUALITY", "82"))
# Alt text and credit are written by a human in .env. The app never invents a
# description of a photo it cannot see, and never claims an official source.
PHOTO_ALT = os.environ.get("PHOTO_ALT", "BLUE COURT編集部が用意した横浜のサッカー写真")
PHOTO_CREDIT = os.environ.get("PHOTO_CREDIT", "").strip()
PHOTO_REUSE = os.environ.get("PHOTO_REUSE", "1") not in ("0", "false", "False")

# --- git publishing ---------------------------------------------------------
GIT_PUSH = os.environ.get("GIT_PUSH", "0") in ("1", "true", "True")
GIT_BRANCH = os.environ.get("GIT_BRANCH", "main")
GIT_REMOTE = os.environ.get("GIT_REMOTE", "origin")
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "blue-court-bot")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "bot@example.invalid")

# --- scheduler --------------------------------------------------------------
# JST wall-clock time of the daily run, "HH:MM".
PUBLISH_AT = os.environ.get("PUBLISH_AT", "10:10")
RUN_AT_START = os.environ.get("RUN_AT_START", "1") not in ("0", "false", "False")


def drive_configured() -> bool:
    return bool(GDRIVE_FOLDER_ID and GOOGLE_CREDENTIALS and Path(GOOGLE_CREDENTIALS).exists())


def drive_status() -> str:
    """Why Drive is off, without ever printing a credential value."""
    if not GDRIVE_FOLDER_ID:
        return "GDRIVE_FOLDER_ID is not set"
    if not GOOGLE_CREDENTIALS:
        return "GOOGLE_APPLICATION_CREDENTIALS is not set"
    if not Path(GOOGLE_CREDENTIALS).exists():
        return f"service account file not found at {GOOGLE_CREDENTIALS}"
    return "configured"
