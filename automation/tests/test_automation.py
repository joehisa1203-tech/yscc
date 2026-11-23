"""Tests for the blog automation container.

They stub Google Drive, so they run with no credentials and no network.
Break one on purpose (e.g. remove the EXIF stripping in
drive_photos.to_hero_jpeg) and the matching test must fail.
"""
from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from automation.app import config, drive_photos, publisher

FOLDER = drive_photos.FOLDER_MIME


class FakeFiles:
    """Minimal stand-in for service.files() with paging and subfolders."""

    def __init__(self, pages: dict[str, list[list[dict]]]):
        self.pages = pages
        self.queries: list[str] = []

    def list(self, q, pageToken=None, **kwargs):
        self.queries.append(q)
        folder_id = q.split("'")[1]
        batches = self.pages.get(folder_id, [[]])
        index = int(pageToken or 0)
        files = batches[index]
        response = {"files": files}
        if index + 1 < len(batches):
            response["nextPageToken"] = str(index + 1)
        return mock.Mock(execute=lambda: response)


class FakeService:
    def __init__(self, pages):
        self._files = FakeFiles(pages)

    def files(self):
        return self._files


def photo(file_id, name, created):
    return {"id": file_id, "name": name, "mimeType": "image/jpeg", "createdTime": created}


class ListImagesTest(unittest.TestCase):
    def test_walks_subfolders_and_follows_page_tokens(self):
        service = FakeService({
            "root": [
                [photo("a", "a.jpg", "2026-01-02T00:00:00Z"),
                 {"id": "sub", "name": "2026", "mimeType": FOLDER}],
                [photo("b", "b.png", "2026-01-01T00:00:00Z")],
            ],
            "sub": [[photo("c", "c.jpg", "2026-01-03T00:00:00Z"),
                     {"id": "doc", "name": "note.txt", "mimeType": "text/plain"}]],
        })
        images = drive_photos.list_images(service, "root")
        self.assertEqual([i["id"] for i in images], ["b", "a", "c"])  # oldest first
        self.assertNotIn("doc", [i["id"] for i in images])

    def test_ignores_non_image_mime_types(self):
        service = FakeService({"root": [[{"id": "x", "name": "sheet",
                                          "mimeType": "application/vnd.google-apps.spreadsheet"}]]})
        self.assertEqual(drive_photos.list_images(service, "root"), [])


class ChooseTest(unittest.TestCase):
    def test_prefers_a_photo_that_was_never_published(self):
        images = [photo("a", "a.jpg", "1"), photo("b", "b.jpg", "2")]
        ledger = {"photos": [{"fileId": "a", "date": "2026-11-20"}]}
        self.assertEqual(drive_photos.choose(images, ledger)["id"], "b")

    def test_reuses_the_oldest_when_everything_was_published(self):
        images = [photo("a", "a.jpg", "1"), photo("b", "b.jpg", "2")]
        ledger = {"photos": [{"fileId": "a", "date": "2026-11-20"},
                             {"fileId": "b", "date": "2026-11-21"}]}
        self.assertEqual(drive_photos.choose(images, ledger)["id"], "a")

    def test_returns_nothing_when_reuse_is_disabled(self):
        images = [photo("a", "a.jpg", "1")]
        ledger = {"photos": [{"fileId": "a", "date": "2026-11-20"}]}
        with mock.patch.object(config, "PHOTO_REUSE", False):
            self.assertIsNone(drive_photos.choose(images, ledger))


class HeroImageTest(unittest.TestCase):
    def source_jpeg(self) -> bytes:
        image = Image.new("RGB", (4000, 1000), (12, 45, 85))
        exif = Image.Exif()
        exif[0x010F] = "TestCamera"          # Make
        exif[0x8825] = {1: "N", 2: (35, 0, 0)}  # GPS block
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif.tobytes())
        return buffer.getvalue()

    def test_crops_to_the_hero_aspect_ratio(self):
        out = Image.open(io.BytesIO(drive_photos.to_hero_jpeg(self.source_jpeg())))
        self.assertEqual(out.size, (config.PHOTO_WIDTH, config.PHOTO_HEIGHT))

    def test_drops_camera_and_gps_metadata(self):
        # Camera files carry GPS coordinates, and this repository is public.
        source = Image.open(io.BytesIO(self.source_jpeg()))
        self.assertTrue(dict(source.getexif()))
        out = Image.open(io.BytesIO(drive_photos.to_hero_jpeg(self.source_jpeg())))
        self.assertEqual(dict(out.getexif()), {})


class FetchPhotoTest(unittest.TestCase):
    def test_saves_the_file_and_records_it_in_the_ledger(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = Image.new("RGB", (1200, 800))
            buffer = io.BytesIO()
            raw.save(buffer, format="JPEG")
            service = FakeService({"root": [[photo("a", "yokohama.jpg", "1")]]})
            service.files().get = lambda **kwargs: mock.Mock(execute=lambda: {"id": "root", "name": "写真"})
            with mock.patch.object(config, "PHOTO_DIR", root / "assets" / "photos"), \
                 mock.patch.object(config, "PHOTO_LEDGER", root / "data" / "photos.json"), \
                 mock.patch.object(config, "GDRIVE_FOLDER_ID", "rootfolderid"), \
                 mock.patch.object(config, "PHOTO_CREDIT", "撮影: 編集部"), \
                 mock.patch.object(drive_photos, "extract_folder_id", lambda _v: "root"), \
                 mock.patch.object(drive_photos, "build_service", lambda: service), \
                 mock.patch.object(drive_photos, "download", lambda _s, _i: buffer.getvalue()):
                hero = drive_photos.fetch_photo_for("2026-11-23")
            self.assertEqual(hero["src"], "assets/photos/2026-11-23-hero.jpg")
            self.assertEqual(hero["credit"], "撮影: 編集部")
            self.assertTrue((root / "assets" / "photos" / "2026-11-23-hero.jpg").exists())
            ledger = json.loads((root / "data" / "photos.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["photos"][0]["fileId"], "a")


class FolderAccessTest(unittest.TestCase):
    def test_reports_an_unreachable_folder_instead_of_zero_images(self):
        # 共有されていないフォルダは list が空を返すだけなので、0枚と区別できないと
        # 「写真が1枚も無い」と誤読する（2026-11-23に実際に誤読した）。
        class Boom:
            def get(self, **kwargs):
                raise RuntimeError("HttpError 404 File not found")

        service = mock.Mock(files=lambda: Boom())
        with mock.patch.object(config, "GDRIVE_FOLDER_ID", "x" * 20), \
             mock.patch.object(drive_photos, "build_service", lambda: service), \
             mock.patch.object(drive_photos, "extract_folder_id", lambda _v: "nope"):
            self.assertIsNone(drive_photos.fetch_photo_for("2026-11-24"))


class AttachPhotoTest(unittest.TestCase):
    def test_skips_quietly_when_drive_is_not_configured(self):
        with mock.patch.object(config, "GDRIVE_FOLDER_ID", ""):
            self.assertFalse(publisher.attach_photo("2026-11-23"))

    def test_a_drive_failure_does_not_stop_the_article(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts.json"
            posts.write_text(json.dumps({"posts": [{"id": "x", "date": "2026-11-23"}]}), encoding="utf-8")
            def boom(_date):
                raise RuntimeError("drive down")
            with mock.patch.object(config, "POSTS_FILE", posts), \
                 mock.patch.object(config, "drive_configured", lambda: True), \
                 mock.patch.object(drive_photos, "fetch_photo_for", boom):
                self.assertFalse(publisher.attach_photo("2026-11-23"))

    def test_writes_the_hero_into_posts_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts.json"
            posts.write_text(json.dumps({"posts": [{"id": "x", "date": "2026-11-23"}]}), encoding="utf-8")
            hero = {"src": "assets/photos/2026-11-23-hero.jpg", "alt": "写真"}
            with mock.patch.object(config, "POSTS_FILE", posts), \
                 mock.patch.object(config, "drive_configured", lambda: True), \
                 mock.patch.object(drive_photos, "fetch_photo_for", lambda _d: hero):
                self.assertTrue(publisher.attach_photo("2026-11-23"))
            saved = json.loads(posts.read_text(encoding="utf-8"))
            self.assertEqual(saved["posts"][0]["hero"], hero)


class ArticlePageTest(unittest.TestCase):
    def post(self, hero=None):
        data = {"id": "2026-11-23-daily-football", "date": "2026-11-23", "category": "観戦ガイド",
                "title": "テスト記事", "summary": "概要", "body": ["本文"], "sources": []}
        if hero:
            data["hero"] = hero
        return data

    def test_renders_the_photo_and_the_og_image(self):
        daily_blog = publisher.load_daily_blog()
        html = daily_blog.page(self.post({"src": "assets/photos/2026-11-23-hero.jpg",
                                          "alt": "横浜の写真", "credit": "撮影: 編集部"}))
        self.assertIn('src="../assets/photos/2026-11-23-hero.jpg"', html)
        self.assertIn('alt="横浜の写真"', html)
        self.assertIn("撮影: 編集部", html)
        self.assertIn('og:image', html)

    def test_article_without_a_photo_is_unchanged(self):
        daily_blog = publisher.load_daily_blog()
        html = daily_blog.page(self.post())
        self.assertNotIn('<figure class="post-photo">', html)  # the CSS rule is always present
        self.assertNotIn("og:image", html)

    def test_rejects_a_hero_path_outside_the_assets_folder(self):
        daily_blog = publisher.load_daily_blog()
        html = daily_blog.page(self.post({"src": "https://example.com/x.jpg", "alt": "x"}))
        self.assertNotIn('<figure class="post-photo">', html)
        self.assertNotIn("example.com", html)


if __name__ == "__main__":
    unittest.main()
