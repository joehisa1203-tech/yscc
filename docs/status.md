# 現在地（2026-11-23 更新）

## リポジトリとpush先（2026-11-23 決定）

- **push先は `joehisa1203-tech/yscc` だけ**（remote `origin`、SSH）。
- 旧 `softrenzu/ycss` は remote `softrenzu` として参照用に残し、**push URLを無効化**してある
  （`git push softrenzu` はエラーで止まる）。取り込みが必要になったら `git fetch softrenzu` で読むだけ。
- **公開サイト https://blue-court-yscc.onrender.com/ は旧リポジトリにつながったまま。**
  つまり、このリポジトリへpushしてもサイトは更新されない。反映するにはRenderの接続先を
  `joehisa1203-tech/yscc` へ切り替える（利用者の作業。残課題に記載）。
- 両リポジトリで毎日投稿のActionsが動くため、記事の履歴は今後分岐する。片方へ寄せる予定はない。

## 稼働状態（2026-11-23 時点）

- **記事の執筆はOpenAI（`gpt-4.1-mini`）で稼働中。** 2026-11-23の記事から実際にLLM製
  （`data/posts.json` の `writer` フィールドで判別できる）。題材は日付で16種をローテーション。
  - Anthropicは**クレジット残高不足**で呼び出せなかった（400）。VPS上の既存キーのうち
    `JOE/geotool/.env` の鍵は認証は通る、`JOE/HP-wordpress/backend/.env` のAnthropicキーは401で無効。
  - 使っているOpenAIキーは `JOE/HP-wordpress/backend/.env` の `OPENAI_API_KEY` を流用
    （`geotool/.env.save` にも同じ鍵）。`beds24-ai-reply/.env` のOpenAIキーは**期限切れ**で、
    あちらのAI返信が止まっている可能性がある（別案件・未調査）。
  - **2026-11-23: このキーの値をセッションのログに表示してしまった**（`.env` 書き込み後の
    確認でマスク処理が効かなかった）。失効と再発行を提案したが、**利用者の判断で
    継続使用**となった（2026-11-23）。再提案しない。
    - 残るリスクは、記録が外部に渡った場合に残高が使われること。**見張るなら
      https://platform.openai.com/usage の請求額**。急増していたら失効させる。
    - 失効させる場合の差し替え先は3か所（同じ鍵を共用している）:
      `BLOG/ycss/.env`、`JOE/HP-wordpress/backend/.env`、`JOE/geotool/.env.save`。
- **GitHub Actions は検証専用にした（コミットもpushもしない）。** publisher はVPSの1本だけ。
  2026-11-23にpush時のActionsがコミットしてVPSのクローンと食い違ったため、
  `publish.yml` からコミット処理を外し、権限も `contents: read` に落とした。
- **公開サイトの検証を中身で行うようにした**（`scripts/check_live_site.py`）。
  記事の日付が当日以上か、`.env` 等が公開されていないかを見る。古いサイト（onrender）に
  向けると落ちることを確認済み。以前の「トップページに 'JFL 2026' があるか」だけの
  検査は、別リポジトリ由来の古いサイトでも緑になっていた。
- **公開URL: https://joeai.co.jp/yscc/** （このVPSのnginx、`/var/www/yscc` を静的配信、TLSは
  既存の joeai.co.jp 証明書）。WordPress（`https://joeai.co.jp/`）は変更前と同じ応答を確認済み。
  nginx設定の退避先は `/etc/nginx/sites-available/hp.bak-20261123-before-yscc`。
  暫定で開けていた 8099 は `127.0.0.1` に閉じた。
- サブディレクトリ公開のため `/yscc/robots.txt` はクローラーに読まれない（ドメイン直下だけが有効）。
  サイトマップは `https://joeai.co.jp/yscc/sitemap.xml` を直接登録する。

- **このVPS（`x210-131-216-216`）で scheduler を常時起動済み**。
  `ycss-scheduler-1` / `restart: unless-stopped`（VPS再起動後も復帰）。次回実行は毎日 10:10 JST。
- `.env` 作成済み（git管理外）。`GIT_PUSH=1`、push先は remote `origin`（`joehisa1203-tech/yscc`）。
- コンテナからのSSH認証とpushは実機確認済み（`ssh -T git@github.com` で
  `Hi joehisa1203-tech!`、`git push --dry-run` が通る）。
  使う鍵はホストに前からある `~/.ssh/id_ed25519_github`（GitHub登録済み）。
  `~/.ssh` を `/ssh` として読み取り専用でマウントし、`SSH_KEY_FILE` で鍵を選ぶ。
- **写真はまだ付かない**（`GDRIVE_FOLDER_ID` 未設定）。設定した翌日の記事から付く。

状態の確認:

```bash
docker compose ps scheduler
docker compose logs --tail=20 scheduler
```

## 動いているもの

- 公開サイト: https://blue-court-yscc.onrender.com/ （Render。接続先は旧 `softrenzu/ycss`）
- 毎日ブログ: `scripts/daily_blog.py` が JST の日付ごとに記事を1本生成。同じ日の二重投稿はしない。
- 記事の生成経路:
  1. **GitHub Actions** `.github/workflows/publish.yml` … 毎日 10:10 JST 頃。写真なしのテキスト記事。
     push先の `joehisa1203-tech/yscc` でも動く。
  2. **Dockerアプリ** `automation/` … `docker compose up -d scheduler` で毎日 `PUBLISH_AT`。
     Google Driveの写真つき。`GIT_PUSH=1` のときだけpushする（既定はoff）。pushは `origin` へ。
- **Driveのサービスアカウント鍵を配置済み**（2026-11-23、利用者から受領）。
  `secrets/google-service-account.json`（権限600・git管理外）。Drive APIの認証は通る。
  - プロジェクト: `blog-515607` ／ アカウント: `blog-774@blog-515607.iam.gserviceaccount.com`
  - **写真フォルダをこのアドレスに「閲覧者」で共有し、`.env` の `GDRIVE_FOLDER_ID` を
    記入すると写真付きになる**（翌日の記事から）。共有前はこのアカウントから見える
    ファイルが0件なので、写真は付かない。
  `JOE/SNS運用` のDrive連携はOAuth（利用者がブラウザで同意する方式）で、
  ヘッドレスのコンテナからは使えない。ycss用に新規作成が必要。
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

1. **Anthropicのクレジット購入**（https://console.anthropic.com/ → Plans & Billing）。
   claude.aiのサブスクリプション（Pro/Max）とAPIの課金は別。APIはクレジットが必要。
   購入後は何も設定しなくてよい（翌日の10:10から本文がLLM製になる）。
   費用の目安: 運用中の `claude-haiku-5-5` なら月30本で約3円。
   品質を上げたい場合は `.env` の `ANTHROPIC_MODEL` を `claude-opus-5-5` に変える（約150円）。
2. **Google Cloud のサービスアカウント作成とJSON鍵の配置**（`secrets/google-service-account.json`）、
   写真フォルダの共有設定、`.env` の `GDRIVE_FOLDER_ID` 記入。手順は `docs/automation.md`。
3. **公開する写真の権利確認。** Driveに入れた写真はそのまま記事に載る。
4. **push資格情報の用意**（`GIT_PUSH=1` で運用する場合）。SSH鍵かcredential helperのマウント。
5. **Dockerを常時動かすホストの決定。** scheduler は動かし続けないと毎日公開しない。
6. **Renderの接続先切り替え（旧URLを使い続けたい場合のみ）。** 現在Renderは旧 `softrenzu/ycss` を
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

### 未着手（判断済みで手が付いていないもの）

- **独自サブドメインへ移すかどうか（任意）。** いまは `joeai.co.jp/yscc/` で動いている。
  移すと robots.txt が有効になり、WordPressのvhostから独立する。`yscc.joeai.co.jp` は
  別サーバー（162.43.101.99）でWordPressが稼働中なので、`blue-court.joeai.co.jp` 等の
  新規サブドメインを使う。DNS変更は利用者の作業。
  決まったら `sudo bash deploy/setup_nginx.sh <ドメイン>` を実行し、`.env` の
  `SITE_PUBLIC_DIR` と `SITE_BASE_URL` を変える。設定ファイルとスクリプトは用意済み
  （`deploy/`）。nginx 1.28.3・certbot導入済みで、`geo` / `reply` / `sns` など
  joeai.co.jp のサブドメイン運用の前例あり。

### 未着手

- アクセス解析（GA4）、観客数実績の測定は未設定。
- `data/matches.json` の日程は手動更新のまま（自動取得はしない方針）。

## 文書の地図

- `README.md` … サイトの目的・構成・公式情報
- `CLAUDE.md` … 目次とこのリポジトリ固有の地雷
- `docs/automation.md` … Docker自動化アプリの設計・環境変数・Drive設定・運用
