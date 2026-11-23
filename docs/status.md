# 現在地（2026-11-23 更新）

## リポジトリとpush先（2026-11-23 決定）

- **push先は `joehisa1203-tech/yscc` だけ**（remote `origin`、SSH）。
- 旧 `softrenzu/ycss` は remote `softrenzu` として参照用に残し、**push URLを無効化**してある
  （`git push softrenzu` はエラーで止まる）。取り込みが必要になったら `git fetch softrenzu` で読むだけ。
- **公開サイト https://blue-court-yscc.onrender.com/ は旧リポジトリにつながったまま。**
  つまり、このリポジトリへpushしてもサイトは更新されない。反映するにはRenderの接続先を
  `joehisa1203-tech/yscc` へ切り替える（利用者の作業。残課題に記載）。
- 両リポジトリで毎日投稿のActionsが動くため、記事の履歴は今後分岐する。片方へ寄せる予定はない。

## 動いているもの

- 公開サイト: https://blue-court-yscc.onrender.com/ （Render。接続先は旧 `softrenzu/ycss`）
- 毎日ブログ: `scripts/daily_blog.py` が JST の日付ごとに記事を1本生成。同じ日の二重投稿はしない。
- 記事の生成経路:
  1. **GitHub Actions** `.github/workflows/publish.yml` … 毎日 10:10 JST 頃。写真なしのテキスト記事。
     push先の `joehisa1203-tech/yscc` でも動く。
  2. **Dockerアプリ** `automation/` … `docker compose up -d scheduler` で毎日 `PUBLISH_AT`。
     Google Driveの写真つき。`GIT_PUSH=1` のときだけpushする（既定はoff）。pushは `origin` へ。
- 自動テスト: `automation/tests/`（14件）。Driveの認証情報なしで動く。
  2026-11-23時点で、EXIF除去とヒーロー画像のパス検証をわざと壊して落ちることを確認済み。

## 決まっている方針

- **架空の情報を作らない**（試合結果・観客数・残席・選手コメント・募集状況）。根拠は `README.md` の運用方針。
- **非公式ファンメディアとして書く。** クラブ公式を装わない。
- **写真はDriveに入っているものだけを使い、未使用の古い順に1枚ずつ消費する。** ランダム選択にしない理由と
  EXIFを落とす理由は `docs/automation.md`。
- **認証情報が無くてもブログは止めない。** Drive未設定なら写真なしで記事を出す。
- **秘密情報はこちらで生成・記入しない。** `.env` と `secrets/` への記入は利用者本人。

## 残課題

### 利用者（本人）にしかできないこと

1. **Google Cloud のサービスアカウント作成とJSON鍵の配置**（`secrets/google-service-account.json`）、
   写真フォルダの共有設定、`.env` の `GDRIVE_FOLDER_ID` 記入。手順は `docs/automation.md`。
2. **公開する写真の権利確認。** Driveに入れた写真はそのまま記事に載る。
3. **push資格情報の用意**（`GIT_PUSH=1` で運用する場合）。SSH鍵かcredential helperのマウント。
4. **Dockerを常時動かすホストの決定。** scheduler は動かし続けないと毎日公開しない。
5. **Renderの接続先切り替え（公開サイトに反映したい場合）。** 現在Renderは旧 `softrenzu/ycss` を
   見ているため、このリポジトリの変更はサイトに出ない。切り替える場合は、`scripts/daily_blog.py` の
   `BASE`（現在 `https://blue-court-yscc.onrender.com/`）とcanonical・og:url・sitemapのURLも
   新しい公開URLに合わせる必要がある。切り替えないなら、このリポジトリは記事と自動化アプリの
   置き場所として使う。

### 見送った判断（理由ごと残す）

- **旧 `softrenzu/ycss` への追従は行わない。** 2026-11-23に利用者が「joehisa1203のysccにpushで
  それ以外はしない」と決めた。誤pushを防ぐため push URL を無効化済み。
- **公開経路（Actions / Dockerアプリ）を1つに寄せる判断は保留。** 同じ日に二重投稿はしない
  （日付で判定）ため、当面は併存で問題が出ない。寄せるなら、Dockerに寄せる場合は
  `.github/workflows/publish.yml` の `schedule:` を外し、Actionsに寄せる場合はDockerを手動実行にする。

### 未着手

- アクセス解析（GA4）、観客数実績の測定は未設定。
- `data/matches.json` の日程は手動更新のまま（自動取得はしない方針）。

## 文書の地図

- `README.md` … サイトの目的・構成・公式情報
- `CLAUDE.md` … 目次とこのリポジトリ固有の地雷
- `docs/automation.md` … Docker自動化アプリの設計・環境変数・Drive設定・運用
