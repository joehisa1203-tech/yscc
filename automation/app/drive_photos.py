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


def choose(images: list[dict], ledger: dict, exclude: set[str] | None = None) -> dict | None:
    """Oldest photo that has never been published; else the oldest used one.

    `exclude` は他の下書きに付いている写真。同じ写真が2本の下書きに付くのを防ぐ。
    """
    exclude = exclude or set()
    used = {entry["fileId"]: entry for entry in ledger.get("photos", [])}
    candidates = [item for item in images if item["id"] not in exclude]
    for item in candidates:
        if item["id"] not in used:
            return item
    if not config.PHOTO_REUSE or not candidates:
        return None
    oldest = sorted(candidates, key=lambda f: used[f["id"]]["date"] if f["id"] in used else "")
    return oldest[0]


def folder_images() -> list[dict] | None:
    """Every image in the configured folder, oldest first. None = the folder is unreachable."""
    folder_id = extract_folder_id(config.GDRIVE_FOLDER_ID)
    service = build_service()
    # 共有されていないフォルダは list が空を返すだけなので、「0枚」と
    # 「そもそも届いていない」が区別できない。先にフォルダ自体を引く。
    try:
        folder = service.files().get(
            fileId=folder_id, fields="id,name", supportsAllDrives=True
        ).execute()
    except Exception as error:
        print("[DRIVE] フォルダに届きません。サービスアカウントへの共有を確認してください: "
              f"{str(error)[:120]}")
        return None
    images = list_images(service, folder_id)
    print(f"[DRIVE] folder {folder.get('name')!r}: {len(images)} images")
    return images


def stage(file_id: str, destination: Path) -> int:
    """Download one Drive image, convert it to the hero JPEG and write it. Returns bytes written."""
    jpeg = to_hero_jpeg(download(build_service(), file_id))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(jpeg)
    return len(jpeg)


def thumbnail_jpeg(raw: bytes, width: int = 480) -> bytes:
    """Small preview for the admin photo picker. Metadata is dropped here as well."""
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((width, width))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=75)
    return out.getvalue()


def pick_for_draft(exclude: set[str]) -> dict | None:
    """The photo a new draft gets automatically: {"fileId", "driveName"} or None."""
    images = folder_images()
    if not images:
        if images == []:
            print("[DRIVE] フォルダは見えていますが画像がありません（JPEG/PNG/WebP/HEICのみ対象）")
        return None
    picked = choose(images, load_ledger(), exclude)
    if not picked:
        print("[DRIVE] every photo has been used (or is on another draft) and PHOTO_REUSE is off")
        return None
    return {"fileId": picked["id"], "driveName": picked.get("name", "")}


def record_published(file_id: str, drive_name: str, date: str, src: str) -> None:
    """公開した写真を台帳に記録する。台帳は「公開中の写真」の一覧で、下書きの写真は入れない。"""
    ledger = load_ledger()
    photos = [e for e in ledger.get("photos", []) if e.get("src") != src]
    photos.insert(0, {
        "fileId": file_id,
        "driveName": drive_name,
        "date": date,
        "src": src,
        "fetchedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    ledger["photos"] = photos
    save_ledger(ledger)


def forget_published(src: str) -> dict | None:
    """非公開にした記事の写真を台帳から外し、その記録を返す（再公開時に使う）。"""
    ledger = load_ledger()
    kept, removed = [], None
    for entry in ledger.get("photos", []):
        if entry.get("src") == src and removed is None:
            removed = entry
        else:
            kept.append(entry)
    if removed is not None:
        ledger["photos"] = kept
        save_ledger(ledger)
    return removed
