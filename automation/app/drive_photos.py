"""Pull one unused photo per day from a Google Drive folder.

Design follows softrenzu/wp-ai-bot (bot/image_featured.py) for the service
account + recursive folder walk, and softrenzu/Rooomphotoskills
(rooomphotos/drive.py) for shared-drive support and paging.

Differences that matter here:
- photos are consumed oldest-first and recorded in data/photos.json, so the
  same picture is not reposted while unused ones remain;
- EXIF is dropped on re-encode. Camera files carry GPS coordinates and device
  serials, and this repository is public.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image

from . import config

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
FOLDER_MIME = "application/vnd.google-apps.folder"


def extract_folder_id(value: str) -> str:
    """Accept either a raw folder id or a pasted Drive folder URL."""
    value = value.strip()
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        return value
    raise ValueError("GDRIVE_FOLDER_ID をフォルダID/URLとして認識できません")


def build_service():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_images(service, root_folder_id: str) -> list[dict]:
    """Walk the folder tree breadth-first and return every image file."""
    found: list[dict] = []
    queue = [root_folder_id]
    seen_folders: set[str] = set()
    while queue:
        folder_id = queue.pop(0)
        if folder_id in seen_folders:
            continue
        seen_folders.add(folder_id)
        page_token = None
        while True:
            response = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken,files(id,name,mimeType,createdTime,modifiedTime)",
                    pageSize=200,
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files", []):
                mime = item.get("mimeType", "")
                if mime == FOLDER_MIME:
                    queue.append(item["id"])
                elif mime in IMAGE_MIMES:
                    found.append(item)
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    found.sort(key=lambda f: (f.get("createdTime", ""), f["id"]))
    return found


def download(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def to_hero_jpeg(raw: bytes) -> bytes:
    """Centre-crop to the hero aspect ratio and re-encode without metadata."""
    image = Image.open(io.BytesIO(raw))
    image = image.convert("RGB")  # drops alpha; also drops the EXIF block
    target_w, target_h = config.PHOTO_WIDTH, config.PHOTO_HEIGHT
    width, height = image.size
    scale = max(target_w / width, target_h / height)
    resized = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    cropped = resized.crop((left, top, left + target_w, top + target_h))
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=config.PHOTO_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


# --- ledger -----------------------------------------------------------------

def load_ledger() -> dict:
    if config.PHOTO_LEDGER.exists():
        return json.loads(config.PHOTO_LEDGER.read_text(encoding="utf-8"))
    return {"photos": []}


def save_ledger(ledger: dict) -> None:
    config.PHOTO_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    config.PHOTO_LEDGER.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def choose(images: list[dict], ledger: dict) -> dict | None:
    """Oldest photo that has never been published; else the oldest used one."""
    used = {entry["fileId"]: entry for entry in ledger.get("photos", [])}
    for item in images:
        if item["id"] not in used:
            return item
    if not config.PHOTO_REUSE or not images:
        return None
    oldest = sorted(images, key=lambda f: used[f["id"]]["date"] if f["id"] in used else "")
    return oldest[0]


def fetch_photo_for(date: str) -> dict | None:
    """Download and store one photo for `date`. Returns hero metadata or None."""
    folder_id = extract_folder_id(config.GDRIVE_FOLDER_ID)
    service = build_service()
    images = list_images(service, folder_id)
    print(f"[DRIVE] {len(images)} images under the folder")
    if not images:
        return None
    ledger = load_ledger()
    picked = choose(images, ledger)
    if not picked:
        print("[DRIVE] every photo has been used and PHOTO_REUSE is off")
        return None
    raw = download(service, picked["id"])
    jpeg = to_hero_jpeg(raw)
    config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date}-hero.jpg"
    (config.PHOTO_DIR / filename).write_bytes(jpeg)
    src = f"{config.PHOTO_WEB_DIR}/{filename}"
    ledger.setdefault("photos", []).insert(
        0,
        {
            "fileId": picked["id"],
            "driveName": picked.get("name", ""),
            "date": date,
            "src": src,
            "fetchedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
    )
    save_ledger(ledger)
    print(f"[DRIVE] saved {src} ({len(jpeg) // 1024} KB) from {picked.get('name', '')}")
    hero = {"src": src, "alt": config.PHOTO_ALT}
    if config.PHOTO_CREDIT:
        hero["credit"] = config.PHOTO_CREDIT
    return hero
