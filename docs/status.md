# 現在地（2026-11-23 更新）

## リポジトリとpush先（2026-11-23 決定）

- **push先は `joehisa1203-tech/yscc` だけ**（remote `origin`、SSH）。
- 旧 `softrenzu/ycss` は remote `softrenzu` として参照用に残し、**push URLを無効化**してある
  （`git push softrenzu` はエラーで止まる）。取り込みが必要になったら `git fetch softrenzu` で読むだけ。
- 旧 `softrenzu/ycss` につながっている Render（`blue-court-yscc.onrender.com`）は**使わない**。
  公開はこのVPSのnginxが行う（pushを待たずに、記事ができた時点で公開される）。
  Renderの接続先を切り替える予定はない。

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
  記事の日付が当日以上か、`.env` 等が公開されていないかを見る。以前の「トップページに
  'JFL 2026' があるか」だけの検査は、別リポジトリ由来の古いサイトでも緑になっていた。
  - **わざと落として確認する方法:** `CHECK_ATTEMPTS=1 python3 scripts/check_live_site.py
    https://joeai.co.jp/`（記事が無いURL）で終了コード1になる。2026-11-23に確認済み。
    `CHECK_ATTEMPTS` を付けないと浸透待ちで30秒×10回かかる。
  - 旧 Render（`blue-court-yscc.onrender.com`）は**落とす材料に使えない**。旧リポジトリ側の
    Actionsが今も毎日投稿しているため、当日の記事が存在して緑になる。
- **公開URL: https://yscc.joeai.co.jp/ （2026-11-23に移行完了）。** このVPSのnginxが
  `/var/www/yscc` を静的配信。TLSは Let's Encrypt（`yscc.joeai.co.jp`、2027-02-21まで、
  certbotが自動更新）。構成は `docs/automation.md`。
  - 利用者がXserverでAレコードを `162.43.101.99` → `210.131.216.216` に変更。これにより
    **別サーバーで動いていたWordPress「yscc」はこのURLでは届かなくなった**（中身は別サーバーに残存）。
  - 旧URL `https://joeai.co.jp/yscc/` は、まず301だけを返す形にし、**同日に利用者の判断で
    設定ごと削除した**（現在404）。`hp` vhost に `/yscc` の記述は残っていない。
    退避は `/home/ubuntu/backups/hp.bak-20261123-235942-before-removing-301`。
    - これにより、旧URLのブックマークや検索結果から来た人は新URLへ飛べず、
      WordPressの404に落ちる。**承知の上での判断**（下記「見送った判断」）。
  - 独立ドメインになったので **`robots.txt` が有効になった**（サブパス時代は無視されていた）。
    サイトマップは `https://yscc.joeai.co.jp/sitemap.xml`。
  - WordPress（`https://joeai.co.jp/`）と `geo` / `sns` / `reply` は移行前と同じ応答を確認済み。
  - nginx設定の退避先: `/home/ubuntu/backups/nginx-20261123-232831.tar.gz`（展開して差分一致を確認）、
    `/home/ubuntu/backups/hp.bak-*-before-301`。暫定で開けていた 8099 は `127.0.0.1` に閉じた。

- **このVPS（`x210-131-216-216`）で scheduler を常時起動済み**。
  `ycss-scheduler-1` / `restart: unless-stopped`（VPS再起動後も復帰）。次回実行は毎日 10:10 JST。
- `.env` 作成済み（git管理外）。`GIT_PUSH=1`、push先は remote `origin`（`joehisa1203-tech/yscc`）。
- コンテナからのSSH認証とpushは実機確認済み（`ssh -T git@github.com` で
  `Hi joehisa1203-tech!`、`git push --dry-run` が通る）。
  使う鍵はホストに前からある `~/.ssh/id_ed25519_github`（GitHub登録済み）。
  `~/.ssh` を `/ssh` として読み取り専用でマウントし、`SSH_KEY_FILE` で鍵を選ぶ。
- **写真を有効にした（2026-11-27）。** `GDRIVE_FOLDER_ID` は**共有ドライブ**
  `0AFGswpd8d-V7Uk9PVA`（「Y.S.C.C._BLOG」）。アプリの `list_images` は
  `supportsAllDrives` / `includeItemsFromAllDrives` を付けているので、共有ドライブでも改修なしで動いた。
  - 中身は現在1枚のみ（`ネクストマッチ.png`＝11/28戦の告知画像）。2026-11-27の記事に掲載済み。
  - **これは写真ではなく告知画像で、16:9に切り出すと日付・会場・上部の「NEXT」が欠ける。**
    両クラブのエンブレムも入る。懸念を伝えたうえで、**利用者の判断で「このまま公開」**となった
    （2026-11-27）。再提案しない。
  - **`PHOTO_REUSE` を `1` → `0` に変えた。** 1枚しかない状態で再利用を許すと、同じ告知画像が
    毎日使い回され、11/28を過ぎても「NEXT MATCH」が出続ける。0なら使い切ったあとは写真なしに戻る。
    写真を複数入れたら `1` に戻してよい。
  - `PHOTO_ALT` はこの画像に合わせて「2026年11月28日のヴィアティン三重戦を告知する画像」にした。
    **altは全写真で共通**なので、実際の写真を入れるときは必ず書き換える。

状態の確認:

```bash
docker compose ps scheduler
docker compose logs --tail=20 scheduler
```

## 動いているもの

- 公開サイト: https://yscc.joeai.co.jp/ （このVPSのnginxが `/var/www/yscc` を配信）
- 毎日ブログ: `scripts/daily_blog.py` が JST の日付ごとに記事を1本生成。同じ日の二重投稿はしない。
- **記事を作って公開するのはVPSのコンテナ1本だけ**（`automation/`、毎日 `PUBLISH_AT`）。
  LLMが本文を書き、Driveの写真を付け、`/var/www/yscc` へ複製し、`origin` へpushする。
  GitHub Actions は検証専用で、記事を作らずpushもしない。
- **全経路の通し試験を実施（2026-11-23 17:00 JST）。** schedulerが時刻どおりに起動し、
  LLMが本文を書き、Driveから写真を取り、ページ生成→push→公開サイト反映まで1回で通った。
  ログ: `[LLM] wrote: ...` → `[DRIVE] folder 'つくば写真': 24 images` →
  `[DRIVE] saved ... (205 KB)` → `[GIT] pushed`。公開サイトで写真つき記事を確認。
  - 試験後、**テスト写真は記事・リポジトリ・台帳から削除し、`GDRIVE_FOLDER_ID` も空に戻した**
    （この写真は民泊・不動産の物件写真で、サッカーの記事に載せる内容ではないため）。
  - つまり**残っているのはサッカー写真のフォルダを用意することだけ**。フォルダIDを
    `.env` に入れて `docker compose up -d --force-recreate scheduler` すれば写真つきになる。

- **Driveのサービスアカウント鍵を配置済み**（2026-11-27に専用プロジェクトの鍵へ差し替え、
  利用者から受領）。`secrets/google-service-account.json`（権限600・git管理外）。
  - プロジェクト: `yscc-blog` ／ **アカウント: `yscc-blog-reader@yscc-blog.iam.gserviceaccount.com`**
  - 認証とDrive APIの呼び出しは実機確認済み（トークン取得成功、`files.list` が200で0件）。
    **0件は「まだ共有されていない」状態で、鍵としては正常。**
  - **写真フォルダをこのアドレスに「閲覧者」で共有し、`.env` の `GDRIVE_FOLDER_ID` を
    記入すると写真付きになる**（翌日の記事から）。
  - **共有は鍵ではなくアカウント単位。** 鍵を入れ替えただけでは見えるファイルは0件のまま。
    古いアカウント（`blog-774@blog-515607...`）に共有していたフォルダがあれば、
    新しいアドレスに共有し直す必要がある。
  - 旧鍵（プロジェクト `blog-515607`）は**退避して置き換えた。鍵を2つ並べて持たない**
    （どちらが使われているか分からなくなる）。退避先:
    `/home/ubuntu/backups/google-service-account.json.bak-20261127-221607-blog-515607`。
    不要になったらGoogle Cloud側で無効化するとよい（利用者の作業）。
  `JOE/SNS運用` のDrive連携はOAuth（利用者がブラウザで同意する方式）で、
  ヘッドレスのコンテナからは使えない。ycss用に新規作成が必要。
- **テストが `.env` の値で落ちた（2026-11-27・修正済み）。** `PHOTO_REUSE=0` にした途端、
  再利用の挙動を見るテストだけが落ちた。テスト側が既定値に頼っていたため。
  `mock.patch.object(config, "PHOTO_REUSE", True)` で明示するようにした。
  **テストは環境変数で結果が変わってはいけない。** `PHOTO_REUSE` を 0 と 1 の両方で
  33件通ることと、再利用の分岐を壊すと落ちることを確認済み。
- **テストが公開サイトを壊す事故があった（2026-11-23・修復済み）。** `export_site()` のテストが
  `SITE_ROOT` だけを差し替えて書き出し先を差し替えていなかったため、publish コンテナの
  `/public`（= `/var/www/yscc`）へ偽のファイルを書き、`index.html` が13バイト・`blog/` が
  1本だけになった。**検査対象も公開先だったのでテストは緑のまま**だった。
  テスト側で `SITE_EXPORT_DIR` を一時ディレクトリに差し替え、書き出し先が一時ディレクトリで
  あること自体を検査するようにした。公開物は `docker compose run --rm publish` で復旧。
  - わざと壊して落ちることを2通りで確認済み（許可リストに `.env` を足す／書き出し先の
    差し替えを外す）。テスト実行の前後で公開ディレクトリが変わらないことも確認した。
- 自動テスト: `automation/tests/`（33件）。Driveの認証情報なしで動く。
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

1. **サッカー写真のDriveフォルダの用意。** `yscc-blog-reader@yscc-blog.iam.gserviceaccount.com` に
   閲覧者で共有し、フォルダIDを伝える（`.env` への記入はこちらで行う）。
   手順は `docs/automation.md`。
2. **公開する写真の権利確認。** Driveに入れた写真はそのまま記事に載る。

### 見送った判断（理由ごと残す）

- **旧 `softrenzu/ycss` への追従は行わない。** 2026-11-23に利用者が「joehisa1203のysccにpushで
  それ以外はしない」と決めた。誤pushを防ぐため push URL を無効化済み。
- **公開経路はVPSのコンテナ1本に寄せた**（2026-11-23）。Actionsにもコミットさせていたため
  片方のpushが拒否され続ける状態になった。`publish.yml` から `schedule:` とコミット処理を外し、
  権限を `contents: read` に落とした。**publisherを2つに戻さない。**
- **新規サブドメイン（`blue-court.joeai.co.jp` 等）の取得は見送った**（2026-11-23）。
  既にDNSに登録済みの `yscc.joeai.co.jp` を向け替えるほうが、利用者の操作が1回で済むため。
- **旧URL（`joeai.co.jp/yscc/`）は配信も301も残さない**（2026-11-23に利用者が決定）。
  2か所で配ると canonical と実体が食い違うため、まず301だけにし、その301も消した。
  **旧URLのブックマークと検索結果からの流入は新URLへ繋がらず404になる**ことは承知の上。
  再提案しないこと。復活させたい場合の退避先は上記（`hp.bak-*-before-removing-301`）。
- **別サーバー（162.43.101.99、Xserver）のWordPress「yscc」はそのまま残す**（2026-11-23に
  利用者が決定）。DNSを向け替えたので `yscc.joeai.co.jp` では届かないが、あちらのサーバーでは
  動き続けている。**公開サイトには影響しない**ため、停止・削除はしない。
  再提案しないこと。もしDNSを元に戻せば、あのWordPressが再びこのURLで見える。

### 未着手

- アクセス解析（GA4）、観客数実績の測定は未設定。
- `data/matches.json` の日程は手動更新のまま（自動取得はしない方針）。

## 文書の地図

- `README.md` … サイトの目的・構成・公式情報
- `CLAUDE.md` … 目次とこのリポジトリ固有の地雷
- `docs/automation.md` … Docker自動化アプリの設計・環境変数・Drive設定・運用
