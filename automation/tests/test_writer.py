"""Tests for the Claude-written article path.

They stub the API client, so they run with no key and no network.
Break a guardrail on purpose (remove a pattern from writer.BANNED) and the
matching test must fail.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation.app import config, publisher, writer


def good_article(**overrides) -> dict:
    article = {
        "category": "観戦ガイド",
        "title": "スタジアムに着いてから試合開始までの過ごし方",
        "summary": "開場からキックオフまでの時間も観戦の一部です。初めてでも落ち着いて楽しむための順番を整えました。",
        "body": [
            "初めてのスタジアムでは、席を探す時間や飲み物を買う時間が思ったよりかかります。開場時刻は試合ごとに違うので、公式の案内を見てから家を出る時間を決めましょう。",
            "席に着いたら、ピッチ全体を一度見渡してみてください。ゴールの位置、ベンチの場所、選手が出てくる入口が分かると、試合が始まってから目で追いやすくなります。",
            "ウォームアップの時間は選手を近くで見られる機会です。パスの速さやシュートの音は、映像では分かりにくい部分なので、早めに着いた人の特権と言えます。",
        ],
    }
    article.update(overrides)
    return article


class FakeResponse:
    """openai の chat.completions.create が返す形の最小版。"""

    def __init__(self, payload, finish_reason="stop"):
        message = mock.Mock(content=json.dumps(payload, ensure_ascii=False))
        self.choices = [mock.Mock(finish_reason=finish_reason, message=message)]


class FakeClient:
    def __init__(self, payload, finish_reason="stop"):
        self.payload = payload
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    class _Completions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.calls.append(kwargs)
            if isinstance(self.outer.payload, Exception):
                raise self.outer.payload
            return FakeResponse(self.outer.payload, self.outer.finish_reason)

    @property
    def chat(self):
        return mock.Mock(completions=self._Completions(self))


class GuardrailTest(unittest.TestCase):
    def test_a_clean_article_passes(self):
        self.assertEqual(writer.check(good_article(), []), [])

    def test_rejects_an_invented_scoreline(self):
        article = good_article()
        article["body"][0] = "前節は2-1で勝利しました。" + article["body"][0]
        self.assertTrue(any("スコア" in p for p in writer.check(article, [])))

    def test_rejects_an_invented_attendance(self):
        article = good_article()
        article["body"][1] = "この日は3200人が集まりました。" + article["body"][1]
        self.assertTrue(writer.check(article, []))

    def test_rejects_an_invented_price(self):
        article = good_article()
        article["body"][1] = "当日券は2000円です。" + article["body"][1]
        self.assertTrue(any("料金" in p for p in writer.check(article, [])))

    def test_rejects_a_fabricated_quote(self):
        article = good_article()
        article["body"][2] = "監督は『次も勝ちます』と語った。" + article["body"][2]
        self.assertTrue(writer.check(article, []))

    def test_rejects_futsal_content(self):
        # .github/workflows/publish.yml fails the build on these words.
        article = good_article()
        article["body"][0] = "フットサルの試合も見に行きましょう。" + article["body"][0]
        self.assertTrue(any("フットサル" in p for p in writer.check(article, [])))

    def test_rejects_an_off_list_category(self):
        self.assertTrue(writer.check(good_article(category="お知らせ"), []))

    def test_rejects_a_repeated_title(self):
        article = good_article()
        self.assertTrue(writer.check(article, ["2026年11月22日のYSCC観戦ノート｜" + article["title"]]))

    def test_rejects_too_few_paragraphs(self):
        article = good_article()
        article["body"] = article["body"][:1]
        self.assertTrue(writer.check(article, []))


class WriteArticleTest(unittest.TestCase):
    def test_returns_the_article_and_sends_the_schema(self):
        client = FakeClient(good_article())
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-real"}):
            article = writer.write_article("2026-11-24", ["前の記事"], client=client)
        self.assertEqual(article["category"], "観戦ガイド")
        sent = client.calls[0]
        self.assertEqual(sent["response_format"]["type"], "json_schema")
        self.assertTrue(sent["response_format"]["json_schema"]["strict"])
        system, user = sent["messages"]
        self.assertIn("スコア", system["content"])        # prohibitions are sent
        self.assertIn("前の記事", user["content"])        # avoids repeats

    def test_returns_none_without_a_key(self):
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertIsNone(writer.write_article("2026-11-24", []))

    def test_returns_none_when_the_api_fails(self):
        client = FakeClient(RuntimeError("503 overloaded"))
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-real"}):
            self.assertIsNone(writer.write_article("2026-11-24", [], client=client))

    def test_returns_none_on_a_truncated_or_refused_answer(self):
        client = FakeClient(good_article(), finish_reason="length")
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-real"}):
            self.assertIsNone(writer.write_article("2026-11-24", [], client=client))

    def test_returns_none_when_a_guardrail_trips(self):
        bad = good_article()
        bad["body"][0] = "前節は3-0で勝利しました。" + bad["body"][0]
        client = FakeClient(bad)
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-real"}):
            self.assertIsNone(writer.write_article("2026-11-24", [], client=client))


class EditProblemsTest(unittest.TestCase):
    """管理画面で人が直した記事の判定。"""

    def test_a_short_human_edit_is_publishable(self):
        # 段落の長さはLLMの品質管理なので、人の編集には課さない。
        article = {"category": "試合情報", "title": "次のホーム戦", "summary": "三ツ沢へ行こう。",
                   "body": ["短い段落でもよい。"]}
        self.assertEqual(writer.edit_problems(article), [])

    def test_a_human_cannot_publish_an_invented_scoreline_either(self):
        article = {"category": "観戦ガイド", "title": "快勝", "summary": "要約",
                   "body": ["Y.S.C.C.は2-1で勝利した。"]}
        found = writer.edit_problems(article)
        self.assertTrue(any("スコア" in p for p in found))
        self.assertTrue(any("試合結果" in p for p in found))

    def test_rejects_an_empty_body(self):
        self.assertTrue(writer.edit_problems({"category": "観戦ガイド", "title": "a",
                                              "summary": "b", "body": ["  "]}))


class ExportSiteTest(unittest.TestCase):
    # SITE_EXPORT_DIR も必ず差し替える。SITE_ROOT だけ差し替えると、公開先の既定値
    # （コンテナでは /public = /var/www/yscc）へ偽のファイルを書き出し、**公開中のサイトを
    # 壊す**。2026-11-23に実際に起き、index.html が 13バイトの "<html></html>" に、
    # blog/ が a.html 1本だけになった。しかも検査対象が公開先だったため、テストは緑のまま
    # 通っていた（偽のファイルが「コピーされた」ので assert が満たされてしまう）。
    def test_copies_public_files_and_leaves_secrets_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            export = Path(tmp) / "public"
            (root / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / ".env").write_text("OPENAI_API_KEY=must-not-be-published", encoding="utf-8")
            (root / "secrets").mkdir()
            (root / "secrets" / "key.json").write_text("{}", encoding="utf-8")
            (root / "blog").mkdir()
            (root / "blog" / "a.html").write_text("a", encoding="utf-8")
            (root / "admin-data").mkdir()
            (root / "admin-data" / "drafts.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(config, "SITE_ROOT", root), \
                 mock.patch.object(config, "SITE_EXPORT_DIR", export):
                target = publisher.export_site()
            # 書き出し先が差し替えた一時ディレクトリであること自体を検査する。
            # ここを見ていないと、公開先へ書いていても気づけない。
            self.assertEqual(target, export)
            self.assertTrue((target / "index.html").exists())
            self.assertTrue((target / "blog" / "a.html").exists())
            self.assertFalse((target / ".env").exists())
            self.assertFalse((target / "secrets").exists())
            # 下書きと管理者のパスワードハッシュは公開しない。
            self.assertFalse((target / "admin-data").exists())


if __name__ == "__main__":
    unittest.main()
