# BLUE COURT（Y.S.C.C.横浜 JFL応援メディア）

静的サイト + 毎日ブログの半自動公開（自動で下書き → 管理画面の公開ボタン）。公開URLは **https://yscc.joeai.co.jp/**
（このVPSのnginxが `/var/www/yscc` を配信。vhostは `yscc.joeai.co.jp`、TLSはLet's Encrypt）。
旧URL `joeai.co.jp/yscc/` は**設定ごと削除した（404）**。`hp` vhostに `/yscc` を戻さない。

**push先は `joehisa1203-tech/yscc`（remote `origin`）だけ。** 旧 `softrenzu/ycss` は remote
`softrenzu` として参照用に残し、push URLを無効化してある。公開はVPSのnginxで、
GitHubへのpushは記録用（Renderは使っていない。`docs/status.md` 参照）。

## 目次

| 文書 | 内容 |
|---|---|
| `README.md` | サイトの目的・構成・公式情報リンク |
| `docs/status.md` | **現在地・決まっている方針・残課題**（まずここを読む） |
| `docs/automation.md` | 下書きを作る側（AI執筆・Drive写真・環境変数・nginx構成） |
| `docs/admin.md` | **管理画面と公開ボタン**（流れ・ログインの守り・管理者アカウント・本番nginx） |

## このリポジトリ固有の地雷

- **記事を公開するのは管理画面の公開ボタンだけ。** scheduler は下書きを作るだけで、
  `posts.json` に入れない。自動公開の経路を戻さない（利用者が2026-11-28に半自動を選んだ）。
  Actionsは検証専用。`.github/workflows/publish.yml` に `schedule:` やコミット処理を戻さない。
  publisherが2つあると、片方のpushが拒否され続ける状態に必ず行き着く（2026-11-23に実際に発生）。
  `DraftIsNotPublicTest` が「下書き作成で何も公開しない」ことを確認する。
- **`admin-data/`（下書き・管理者のパスワードハッシュ）を git にも公開ディレクトリにも入れない。**
  リポジトリは公開なので、未確認の下書きがGitHubで読めてしまう。`.gitignore` と
  `export_site()` の許可リストで止めている。
- **コードを変えたら scheduler と admin を `--force-recreate` する。** scheduler は起動時に読んだ
  モジュールのまま動くので、作り直さないと古い挙動（2026-11-28以前なら自動公開）が続く。
- **管理画面の gunicorn を2プロセス以上にしない。** ログイン失敗の回数をメモリで数えているので、
  プロセスごとに分かれて回数制限が効かなくなる。
- **Webサーバーにリポジトリのディレクトリを向けない。** `.env` が公開される。
  公開は `site/`（`publisher.export_site()` の許可リスト）だけ。
- **LLMが書いた本文は禁止表現チェックで捨てられる。人が管理画面で直した本文も同じ `BANNED` で
  公開を止める**（`writer.edit_problems`）。判定は `automation/app/writer.py` の
  `BANNED`。パターンを消すとテストが落ちる（`automation/tests/test_writer.py`）。
  執筆は OpenAI（`gpt-4.1-mini`）。**事業者の呼び出しを2つ並べて持たない**（どちらが
  使われているか分からなくなる）。戻すなら置き換える。
- **架空の情報を書かない。** 試合結果、観客数、チケット残席、選手コメント、募集状況は生成しない。
  記事テンプレートは `scripts/daily_blog.py` の `TIPS`（`grep -n "^TIPS" scripts/daily_blog.py`）。
- **試合日程は自動更新されない。** `data/matches.json` は公式サイトを見て手で直す。
- **フットサル（F.LEAGUE）の内容を混ぜない。** `.github/workflows/publish.yml` の検証ステップが
  `ysccfutsal` / `fleague.jp` / `F.LEAGUE` を検出して失敗する。
- **写真は権利を確認したものだけ。** Driveフォルダに入れた写真はそのまま公開記事に載る。
  クラブ公式写真・第三者の写真を無確認で入れない。
- **秘密情報を書かない。** `.env` と `secrets/` はgit管理外。鍵の値を画面やコミットに出さない。
  `grep -r` は `.gitignore` 対象を外すので、秘密情報の点検には `command grep -r` を使う。
- **コンテナはリポジトリに直接書き込む。** `.env` の `HOST_UID` / `HOST_GID` をホストの
  `id -u` / `id -g` に合わせないと、生成ファイルがroot所有になって以降の操作が失敗する。
- **テストを公開ディレクトリに書かせない。** `export_site()` のテストは `SITE_ROOT` だけでなく
  **`SITE_EXPORT_DIR` も差し替える**。差し替え忘れると publish コンテナの `/public`
  （= `/var/www/yscc`）へ偽のファイルを書き出し、**公開中のサイトを壊す**。2026-11-23に実際に
  起き、`index.html` が13バイトの `<html></html>`、`blog/` が `a.html` 1本だけになった。
  しかも検査対象が公開先になるため**テストは緑のまま通る**。
  `automation/tests/test_writer.py` の `ExportSiteTest` は書き出し先が一時ディレクトリで
  あること自体を検査する（`assertEqual(target, export)`）。ここを外すと落ちる。
- CSSは `styles.css`（元デザイン）と `football.css`（サッカー版の上書き）の2枚。
  **新しい色・角丸・影を発明しない。** 既存の変数（`:root` の `--navy` 等）を使う。

## 確認コマンド

```bash
docker compose up -d --force-recreate scheduler admin  # .env を変えたとき（restartでは反映されない）
docker compose up -d --force-recreate scheduler admin  # コードを変えたとき（build の後）
docker compose run --rm publish                  # 今日の下書きを作る（公開はしない）
docker compose run --rm --entrypoint python publish -m unittest discover -s automation/tests -t .
docker compose up -d preview                     # http://localhost:8099/
```
