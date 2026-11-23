# 現在地（2026-11-23 更新）

## 動いているもの

- 公開サイト: https://blue-court-yscc.onrender.com/ （Render、mainへのpushで自動デプロイ）
- 毎日ブログ: `scripts/daily_blog.py` が JST の日付ごとに記事を1本生成。同じ日の二重投稿はしない。
- 公開経路（現在2つ）:
  1. **GitHub Actions** `.github/workflows/publish.yml` … 毎日 10:10 JST 頃。写真なしのテキスト記事。
  2. **Dockerアプリ** `automation/` … `docker compose up -d scheduler` で毎日 `PUBLISH_AT`。
     Google Driveの写真つき。`GIT_PUSH=1` のときだけpushする（既定はoff）。
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

### 判断が必要（未決）

- **公開経路を1つに寄せるかどうか。** 現在は GitHub Actions と Dockerアプリの両方が同じ記事を作れる。
  二重投稿はしない（日付で判定）が、運用を2か所で追うことになる。
  - Dockerに寄せる → `.github/workflows/publish.yml` の `schedule:` を外す。写真つき記事が毎日出る。
    ただし常時稼働ホストが要る。
  - Actionsに寄せる → Dockerは手動実行（写真を足したいときだけ）に使う。
  未決のまま両方を動かし続けないこと。

### 未着手

- アクセス解析（GA4）、観客数実績の測定は未設定。
- `data/matches.json` の日程は手動更新のまま（自動取得はしない方針）。

## 文書の地図

- `README.md` … サイトの目的・構成・公式情報
- `CLAUDE.md` … 目次とこのリポジトリ固有の地雷
- `docs/automation.md` … Docker自動化アプリの設計・環境変数・Drive設定・運用
