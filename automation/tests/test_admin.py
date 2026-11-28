"""Tests for the semi-automatic flow: drafts, the 公開 button and the admin login.

Everything runs in a temporary copy of the site. sandbox() points **every** path that
can be written — including SITE_EXPORT_DIR (the live /var/www/yscc inside the
container) — at the temporary directory, and checks it did. See CLAUDE.md:
a test that wrote to the export dir once replaced the live site.

Break one on purpose and the matching test must fail, e.g.:
- make drafts.create_for() also call publisher.rebuild_and_ship()  -> DraftIsNotPublicTest
- drop the problems() check from drafts.publish()                   -> PublishTest
- remove limiter.blocked() from the login view                      -> LoginTest
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from PIL import Image

from automation.app import config, drafts, drive_photos, publisher, writer

LLM_ARTICLE = {
    "category": "観戦ガイド",
    "title": "スタジアムに着いてから試合開始までの過ごし方",
    "summary": "開場からキックオフまでの時間も観戦の一部です。初めてでも落ち着いて楽しむための順番を整えました。",
    "body": ["一段落目。" * 10, "二段落目。" * 10, "三段落目。" * 10],
}


@contextmanager
def sandbox(posts: list[dict] | None = None, article: dict | None = LLM_ARTICLE):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        export = Path(tmp) / "public"
        (root / "data").mkdir(parents=True)
        (root / "blog").mkdir()
        (root / "index.html").write_text("<html>top</html>", encoding="utf-8")
        (root / "data" / "posts.json").write_text(
            json.dumps({"posts": posts or []}, ensure_ascii=False), encoding="utf-8")
        patches = [
            mock.patch.object(config, "SITE_ROOT", root),
            mock.patch.object(config, "POSTS_FILE", root / "data" / "posts.json"),
            mock.patch.object(config, "PHOTO_DIR", root / "assets" / "photos"),
            mock.patch.object(config, "PHOTO_LEDGER", root / "data" / "photos.json"),
            mock.patch.object(config, "ADMIN_DATA_DIR", root / "admin-data"),
            mock.patch.object(config, "SITE_EXPORT_DIR", export),
            mock.patch.object(config, "GIT_PUSH", False),
            mock.patch.object(config, "drive_configured", lambda: False),
            mock.patch.object(writer, "write_article", lambda *_a, **_k: article),
        ]
        for patch in patches:
            patch.start()
        try:
            # 書き出し先が一時ディレクトリであること自体を確かめる（公開中のサイトを守る）。
            assert config.SITE_EXPORT_DIR == export and str(export).startswith(tmp)
            yield root, export
        finally:
            for patch in reversed(patches):
                patch.stop()


def jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 900), (10, 40, 80)).save(buffer, format="JPEG")
    return buffer.getvalue()


def posts_in(root: Path) -> list[dict]:
    return json.loads((root / "data" / "posts.json").read_text(encoding="utf-8"))["posts"]


class DraftIsNotPublicTest(unittest.TestCase):
    def test_the_daily_run_makes_a_draft_and_publishes_nothing(self):
        with sandbox() as (root, export):
            draft = drafts.create_for("2026-11-29")
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["headline"], LLM_ARTICLE["title"])
            self.assertEqual(posts_in(root), [])                  # posts.json は変わらない
            self.assertEqual(list((root / "blog").iterdir()), [])  # 記事ページも作らない
            self.assertFalse(export.exists())                     # 公開ディレクトリに触れない

    def test_falls_back_to_the_written_rotation_when_the_llm_declines(self):
        with sandbox(article=None) as (root, _):
            draft = drafts.create_for("2026-11-29")
            self.assertIn("定型", draft["note"])
            self.assertTrue(draft["titlePrefix"].startswith("2026年11月29日"))
            self.assertEqual(drafts.problems(draft), [])

    def test_makes_only_one_draft_per_day(self):
        with sandbox() as _:
            self.assertIsNotNone(drafts.create_for("2026-11-29"))
            self.assertIsNone(drafts.create_for("2026-11-29"))
            self.assertEqual(len(drafts.load()), 1)

    def test_no_draft_when_the_day_is_already_published(self):
        with sandbox(posts=[{"id": "x", "date": "2026-11-29", "title": "t"}]) as _:
            self.assertIsNone(drafts.create_for("2026-11-29"))

    def test_an_unpublished_draft_stays_a_draft_the_next_day(self):
        with sandbox() as (root, _):
            drafts.create_for("2026-11-29")
            drafts.create_for("2026-11-30")
            self.assertEqual([d["date"] for d in drafts.load()], ["2026-11-30", "2026-11-29"])
            self.assertEqual(posts_in(root), [])


class PublishTest(unittest.TestCase):
    def test_publish_puts_the_article_on_the_site(self):
        with sandbox() as (root, export):
            draft = drafts.create_for("2026-11-29")
            result = drafts.publish(draft["id"])
            post = posts_in(root)[0]
            self.assertEqual(post["id"], "2026-11-29-daily-football")
            self.assertEqual(post["title"], "2026年11月29日のYSCC観戦ノート｜" + LLM_ARTICLE["title"])
            self.assertNotIn("status", post)
            self.assertTrue((export / "blog" / "2026-11-29-daily-football.html").exists())
            self.assertEqual(drafts.load(), [])
            self.assertIn("GIT_PUSH", result["git"])

    def test_an_edit_with_an_invented_result_is_not_published(self):
        with sandbox() as (root, export):
            draft = drafts.create_for("2026-11-29")
            found = drafts.update(draft["id"], "観戦ガイド", "快勝", "要約です",
                                  ["Y.S.C.C.は2-1で勝利した。"])
            self.assertTrue(found)
            with self.assertRaises(drafts.DraftError):
                drafts.publish(draft["id"])
            self.assertEqual(posts_in(root), [])
            self.assertFalse(export.exists())
            self.assertEqual(len(drafts.load()), 1)  # 下書きは残る

    def test_edits_are_what_gets_published(self):
        with sandbox() as (root, _):
            draft = drafts.create_for("2026-11-29")
            drafts.update(draft["id"], "試合情報", "三ツ沢で会いましょう", "人が直した要約",
                          ["人が書いた一段落目。", "", "二段落目。"])
            drafts.publish(draft["id"])
            post = posts_in(root)[0]
            self.assertEqual(post["category"], "試合情報")
            self.assertTrue(post["title"].endswith("三ツ沢で会いましょう"))
            self.assertEqual(post["body"], ["人が書いた一段落目。", "二段落目。"])

    def test_the_photo_goes_public_only_when_published(self):
        with sandbox() as (root, export):
            with mock.patch.object(drive_photos, "download", lambda _s, _i: jpeg()), \
                 mock.patch.object(drive_photos, "build_service", lambda: None):
                draft = drafts.create_for("2026-11-29")
                drafts.set_photo(draft["id"], "drivefile0001", "yokohama.jpg")
            self.assertFalse((root / "assets").exists())            # 下書きの写真は公開側に無い
            self.assertFalse((root / "data" / "photos.json").exists())
            drafts.update(draft["id"], "観戦ガイド", LLM_ARTICLE["title"], LLM_ARTICLE["summary"],
                          LLM_ARTICLE["body"], alt="三ツ沢のゴール裏", credit="撮影: 編集部")
            drafts.publish(draft["id"])
            hero = posts_in(root)[0]["hero"]
            self.assertEqual(hero["alt"], "三ツ沢のゴール裏")
            self.assertEqual(hero["credit"], "撮影: 編集部")
            self.assertTrue((export / hero["src"]).exists())
            ledger = json.loads((root / "data" / "photos.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["photos"][0]["fileId"], "drivefile0001")
            self.assertFalse(drafts.photo_path(draft["id"]).exists())


class UnpublishTest(unittest.TestCase):
    def test_unpublish_removes_the_page_and_keeps_a_draft(self):
        with sandbox() as (root, export):
            with mock.patch.object(drive_photos, "download", lambda _s, _i: jpeg()), \
                 mock.patch.object(drive_photos, "build_service", lambda: None):
                draft = drafts.create_for("2026-11-29")
                drafts.set_photo(draft["id"], "drivefile0001", "yokohama.jpg")
            drafts.publish(draft["id"])
            src = posts_in(root)[0]["hero"]["src"]
            drafts.unpublish(draft["id"])
            self.assertEqual(posts_in(root), [])
            self.assertFalse((root / "blog" / "2026-11-29-daily-football.html").exists())
            self.assertFalse((export / "blog" / "2026-11-29-daily-football.html").exists())
            self.assertFalse((export / src).exists())
            back = drafts.get(draft["id"])
            self.assertEqual(back["status"], "unpublished")
            self.assertEqual(back["headline"], LLM_ARTICLE["title"])
            self.assertTrue(drafts.photo_path(draft["id"]).exists())
            ledger = json.loads((root / "data" / "photos.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["photos"], [])
            drafts.publish(draft["id"])                             # 直してもう一度公開できる
            self.assertEqual(posts_in(root)[0]["hero"]["src"], src)


class BuildTest(unittest.TestCase):
    def test_robots_keeps_the_admin_out_of_search(self):
        with sandbox(posts=[]) as (root, _):
            publisher.load_daily_blog().build()
            self.assertIn("Disallow: /admin/", (root / "robots.txt").read_text(encoding="utf-8"))

    def test_build_writes_inside_the_sandbox_only(self):
        # load_daily_blog() が config のパスに向いていないと、本物の data/ と blog/ を書き換える。
        with sandbox(posts=[]) as (root, _):
            module = publisher.load_daily_blog()
            self.assertEqual(module.POSTS, root / "data" / "posts.json")
            self.assertEqual(module.ARTICLES, root / "blog")


# --- web ----------------------------------------------------------------------

def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


class AdminWebCase(unittest.TestCase):
    def setUp(self):
        self.box = sandbox()
        self.root, self.export = self.box.__enter__()
        self.addCleanup(self.box.__exit__, None, None, None)
        cookie = mock.patch.object(config, "ADMIN_COOKIE_SECURE", False)
        cookie.start()
        self.addCleanup(cookie.stop)
        from automation.admin import app as admin_app, auth
        self.auth = auth
        auth.set_password("editor", "correct horse battery")
        self.app = admin_app.create_app()
        self.client = self.app.test_client()

    def login(self, password="correct horse battery", name="editor"):
        page = self.client.get("/admin/login").get_data(as_text=True)
        return self.client.post("/admin/login", data={
            "csrf": csrf_of(page), "username": name, "password": password})

    def token(self, path="/admin/"):
        return csrf_of(self.client.get(path).get_data(as_text=True))


class LoginTest(AdminWebCase):
    def test_every_page_needs_a_login(self):
        for path in ("/admin/", "/admin/drafts/x", "/admin/drafts/x/preview"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/admin/login", response.headers["Location"])

    def test_the_right_password_logs_in(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_a_wrong_password_does_not(self):
        self.assertEqual(self.login("wrong password!!").status_code, 401)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_repeated_failures_lock_out_even_the_right_password(self):
        for _ in range(5):
            self.login("wrong password!!")
        self.assertEqual(self.login().status_code, 429)

    def test_head_requests_are_not_counted_as_failed_logins(self):
        # 死活監視の HEAD で失敗回数が増えると、正しい利用者が締め出される。
        for _ in range(6):
            self.assertEqual(self.client.head("/admin/login").status_code, 200)
        self.assertEqual(self.login().status_code, 302)

    def test_a_post_without_the_form_token_is_refused(self):
        self.login()
        self.assertEqual(self.client.post("/admin/drafts/new").status_code, 400)

    def test_changing_the_password_ends_existing_logins(self):
        self.login()
        self.auth.set_password("editor", "another long password")
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_only_a_hash_is_stored(self):
        stored = (config.ADMIN_DATA_DIR / "users.json").read_text(encoding="utf-8")
        self.assertNotIn("correct horse battery", stored)

    def test_short_passwords_are_refused(self):
        with self.assertRaises(ValueError):
            self.auth.set_password("editor", "short")

    def test_pages_are_not_framed_cached_or_indexed(self):
        response = self.client.get("/admin/login")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")


class PublishButtonTest(AdminWebCase):
    def test_draft_preview_publish_unpublish(self):
        self.login()
        draft = drafts.create_for("2026-11-29")
        page = self.client.get(f"/admin/drafts/{draft['id']}")
        self.assertEqual(page.status_code, 200)
        preview = self.client.get(f"/admin/drafts/{draft['id']}/preview").get_data(as_text=True)
        self.assertIn("プレビュー（未公開）", preview)
        self.assertEqual(posts_in(self.root), [])

        self.client.post(f"/admin/drafts/{draft['id']}", data={
            "csrf": csrf_of(page.get_data(as_text=True)), "action": "publish",
            "category": "観戦ガイド", "headline": "編集した見出し", "summary": "編集した要約",
            "body": "一段落目。\r\n\r\n二段落目。"})
        post = posts_in(self.root)[0]
        self.assertTrue(post["title"].endswith("編集した見出し"))
        self.assertEqual(post["body"], ["一段落目。", "二段落目。"])

        self.client.post(f"/admin/posts/{post['id']}/unpublish", data={"csrf": self.token()})
        self.assertEqual(posts_in(self.root), [])
        self.assertEqual(drafts.get(post["id"])["status"], "unpublished")

    def test_save_does_not_publish(self):
        self.login()
        draft = drafts.create_for("2026-11-29")
        self.client.post(f"/admin/drafts/{draft['id']}", data={
            "csrf": self.token(), "action": "save", "category": "観戦ガイド",
            "headline": "見出し", "summary": "要約", "body": "本文"})
        self.assertEqual(posts_in(self.root), [])
        self.assertEqual(drafts.get(draft["id"])["headline"], "見出し")


if __name__ == "__main__":
    unittest.main()
