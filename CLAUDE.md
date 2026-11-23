# BLUE COURT（Y.S.C.C.横浜 JFL応援メディア）

静的サイト + 毎日ブログ自動生成。

**push先は `joehisa1203-tech/yscc`（remote `origin`）だけ。** 旧 `softrenzu/ycss` は remote
`softrenzu` として参照用に残し、push URLを無効化してある。Renderは旧リポジトリを見ているため、
このリポジトリへのpushでは公開サイトは更新されない（`docs/status.md` 参照）。

## 目次

| 文書 | 内容 |
|---|---|
| `README.md` | サイトの目的・構成・公式情報リンク |
| `docs/status.md` | **現在地・決まっている方針・残課題**（まずここを読む） |
| `docs/automation.md` | Docker版ブログ自動化アプリの設計・環境変数・Drive設定 |

## このリポジトリ固有の地雷

- **毎日の投稿はVPSのコンテナが行う。`.github/workflows/publish.yml` に `schedule:` を戻さない。**
  同時刻に両方が投稿すると、先にActionsがコミットした日はVPS側のpushが拒否され、以後ずっと失敗する。
- **Webサーバーにリポジトリのディレクトリを向けない。** `.env` が公開される。
  公開は `site/`（`publisher.export_site()` の許可リスト）だけ。
- **LLMが書いた本文は禁止表現チェックで捨てられる。** 判定は `automation/app/writer.py` の
  `BANNED`。パターンを消すとテストが落ちる（`automation/tests/test_writer.py`）。
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
- CSSは `styles.css`（元デザイン）と `football.css`（サッカー版の上書き）の2枚。
  **新しい色・角丸・影を発明しない。** 既存の変数（`:root` の `--navy` 等）を使う。

## 確認コマンド

```bash
docker compose run --rm publish                  # 今日の記事を生成
docker compose run --rm --entrypoint python publish -m unittest discover -s automation/tests -t .
docker compose up -d preview                     # http://localhost:8099/
```
