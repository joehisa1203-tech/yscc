# ブログ自動化アプリ（Docker）

## これは何か

`automation/` は、BLUE COURT の毎日ブログを **Dockerコンテナ1つで** 公開するアプリです。

1. その日（JST）の記事を1本用意する
   - `OPENAI_API_KEY` があれば **OpenAIが書く**（`automation/app/writer.py`）
   - 無い・失敗した・禁止表現が出た場合は `scripts/daily_blog.py` の手書き24本から選ぶ
2. Google Drive のフォルダから **まだ使っていない写真を1枚** 取り出し、記事のヒーロー画像にする
3. 記事ページ・`sitemap.xml` を作り直す
4. （任意）git commit → push して Render の自動デプロイを起こす

**Driveもgitも未設定で動きます。** その場合は「写真なしの記事を生成してワーキングツリーに置く」まで。
認証情報が1つ欠けただけでブログが止まらないようにするための設計です。

## 参考にした実装

| 参考 | 取り入れたところ |
|---|---|
| `softrenzu/wp-ai-bot` （`bot/image_featured.py`, `docker-compose.yml`, `bot/scheduler.py`） | サービスアカウントでのDrive認証、フォルダを再帰的に辿る走査、コンテナを用途別サービスに分ける構成 |
| `softrenzu/Rooomphotoskills` （`rooomphotos/drive.py`） | 共有ドライブ対応（`supportsAllDrives`）、`nextPageToken` のページング、フォルダURLからのID抽出 |

参考元と変えた点は3つあり、それぞれ理由があります。

- **写真をランダムに選ばない。** `data/photos.json` に使用済みファイルIDを残し、未使用の古い順に1枚ずつ使います。
  ランダムだと同じ写真が数日おきに出て、毎日更新しているように見えなくなります。
- **EXIFを必ず落とす。** カメラやスマホの写真にはGPS座標や端末情報が入っています。このリポジトリは公開です。
  `automation/tests/test_automation.py::HeroImageTest::test_drops_camera_and_gps_metadata` が番をしています。
- **スケジューラは「JSTの時刻」を狙う。** 参考元は「24時間ごと」にスリープするため、再起動すると投稿時刻がずれていきます。

## 記事の執筆（LLM）

`automation/app/writer.py` が OpenAI の chat completions を **1日1回だけ** 呼びます。

**なぜOpenAIなのか。** 当初はClaudeで実装したが、Anthropicアカウントのクレジット残高が
不足していて呼び出せなかった（400）。このVPSに残高のあるOpenAIキーがあったため、
2026-11-23に呼び出し部分だけを置き換えた。判定・フォールバック・題材ローテーションは
事業者に依存しないので、戻すときも差し替えるのは数十行だけ。**両方の呼び出しを並べて
残していない**（どちらが使われているか分からなくなるため）。

- モデルは `gpt-4.1-mini`（`.env` の `OPENAI_MODEL`）。毎日1本の短い記事ならこれで足りる
- **題材を日付で回す**（`writer.THEMES`、16種）。題材を指定しないと「スタジアム周辺の
  街歩き」のような無難な内容に寄り、3回続けてほぼ同じ記事になった（実測）
- 段落は3つ・各100〜200文字を指示し、60文字未満の段落は破棄する（1文だけの
  締め段落が出て記事全体が落ちたため、下限を40→60文字に調整）
- 出力は JSON Schema で固定（`category` / `title` / `summary` / `body[3-4]`）
- **禁止表現チェックを通らない記事は捨てる。** 判定は `writer.BANNED`:
  スコア・得点・人数・金額・観客数・チケット在庫・試合結果・関係者コメント・
  募集条件・順位確定・フットサル・公式を装う表現。最近のタイトルとの重複も弾く
- 捨てた場合・APIが落ちた場合・キーが無い場合は **手書き24本にフォールバック**する

**なぜ捨てる設計か。** モデルは試合結果も観客数も知りません。それでも書けてしまうため、
「書かせない」だけでは不十分で「出さない」が必要です。重複した記事が出る損害より、
ファンサイトが架空のスコアを載せる損害のほうが大きい、という判断です。
`automation/tests/test_writer.py` が番をしており、`writer.BANNED` から検出パターンを
1つ削ると該当テストが落ちます（2026-11-23に確認済み）。

## 公開用ディレクトリ

`publisher.export_site()` が `site/` に **公開してよいファイルだけ** を複製します
（`PUBLIC_FILES` / `PUBLIC_DIRS` の許可リスト）。拒否リストにしていないのは、
ファイルが増えたときに漏らさないためです。

**リポジトリのディレクトリをそのままWebサーバーに向けないこと。** `.env` が
`https://.../.env` で読めてしまい、APIキーとDrive設定が漏れます。`preview` サービスは
`site/` だけをマウントしています。

```bash
docker compose up -d preview     # http://<このホスト>:8099/（PREVIEW_BIND=127.0.0.1 で内側だけに）
```

## いまの公開構成（2026-11-23〜）

**https://joeai.co.jp/yscc/** で公開しています。既存の `joeai.co.jp`（WordPress）と同じ
nginx vhost にサブパスを1つ足した形で、DNSの変更は不要でした。

```
/etc/nginx/sites-available/hp
  location ^~ /yscc/   → root /var/www;   （= /var/www/yscc を静的配信）
  location = /yscc     → 301 /yscc/
  location /           → WordPress（127.0.0.1:8080）※従来どおり
```

- `.env` の `SITE_PUBLIC_DIR=/var/www/yscc`、`SITE_BASE_URL=https://joeai.co.jp/yscc/`
- 変更前の設定は `/etc/nginx/sites-available/hp.bak-20261123-before-yscc` に退避済み。
  戻すときは `sudo cp -a` で上書きして `sudo systemctl reload nginx`
- `location ^~` は正規表現ロケーションを飛ばすため、隠しファイルの遮断を内側にも置いている
- 暫定で開けていた 8099 は `PREVIEW_BIND=127.0.0.1` で内側に閉じた

**サブディレクトリ公開の制約:** `robots.txt` はドメイン直下（`https://joeai.co.jp/robots.txt`）
しか読まれないため、`/yscc/robots.txt` はクローラーに無視されます。いまはWordPress側の
robots.txtが効いています。検索エンジンにはサイトマップURL
（`https://joeai.co.jp/yscc/sitemap.xml`）を直接登録してください。独自サブドメインに
移せばこの制約は無くなります。

## 独自サブドメインへ移す場合（nginx + Let's Encrypt）

このVPSのnginxで配ります。Render も GitHub Pages も使いません。**pushを待たずに、記事ができた
時点で公開されます。**

順番が大事です。**DNSが先、証明書が後。** Let's Encryptはドメインに80番で接続して所有確認を
するため、DNSが向いていないと証明書が取れません。

1. **（利用者）DNSにAレコードを作る** … 名前は使うサブドメイン、値は `210.131.216.216`。
   `yscc.joeai.co.jp` は別サーバー（162.43.101.99）で稼働中なので、差し替えるとその
   サイトがURLで届かなくなる。新規サブドメインなら影響なし。
2. **（こちら）vhostとTLS**

```bash
sudo bash deploy/setup_nginx.sh <ドメイン>
```

   DNSがこのホストを向いていなければ、何も変更せずに中断します。

3. **（こちら）`.env` を2行変えて再起動**（サブパスからの引っ越しなら、
   `location ^~ /yscc/` を新URLへの301リダイレクトに置き換える）

```
SITE_PUBLIC_DIR=/var/www/blue-court
SITE_BASE_URL=https://<ドメイン>/
```

```bash
docker compose up -d --force-recreate scheduler && docker compose run --rm publish
```

`SITE_PUBLIC_DIR` を `/home/ubuntu` の外に出すのは、`/home/ubuntu` が `drwxr-x---` で
nginx（www-data）が辿れないためです。パーミッションを緩めるより、公開物だけを
`/var/www` に置くほうが安全です。

設定は `deploy/nginx/blue-court.conf.template`。既存サイトの作法に合わせ、隠しファイルと
置き忘れファイルは404にして `blocked.log` に記録します（公開ディレクトリは許可リストで
作っているので本来入っていませんが、二重にしています）。

## `.env` を変えたときの反映

```bash
docker compose up -d --force-recreate scheduler
```

**`docker compose restart` では反映されません。** 環境変数はコンテナ生成時に固定されるため、
`restart` は古い値のまま動き続けます（2026-11-23に実際にこれで取り違えた）。

## 公開状態の確認

```bash
python3 scripts/check_live_site.py                 # 既定は https://joeai.co.jp/yscc/
python3 scripts/check_live_site.py <別のURL>       # 引数で切り替え
```

当日の記事が配信されているかと、`.env` などが公開されていないかを**中身で**確認します。
GitHub Actions（`site-smoke-test.yml`）も同じスクリプトを使います。

## 使い方

```bash
cp .env.example .env     # 中身の記入は利用者本人が行う
docker compose run --rm publish        # 今日の記事を1回だけ生成
docker compose up -d scheduler         # 毎日 PUBLISH_AT(JST) に生成し続ける（常時起動）
docker compose up -d preview           # http://localhost:8099/ で表示確認
docker compose logs -f scheduler       # 動いているかの確認
docker compose down                    # 停止
```

テスト（Driveの認証情報なしで動きます）:

```bash
docker compose run --rm --entrypoint python publish -m unittest discover -s automation/tests -t .
```

## Google Drive の準備（利用者の作業）

1. Google Cloud でプロジェクトを作り、**Google Drive API** を有効化する。
2. サービスアカウントを作り、JSON鍵を作成する。
3. そのJSONを `secrets/google-service-account.json` として置く（`secrets/` はgit管理外）。
4. 写真を入れたDriveフォルダを、サービスアカウントのメールアドレス（`…@….iam.gserviceaccount.com`）に
   **閲覧者** で共有する。
5. `.env` の `GDRIVE_FOLDER_ID` にフォルダIDかフォルダURLを書く。

サブフォルダも再帰的に探します。JPEG / PNG / WebP / HEIC を対象にし、それ以外（ドキュメント等）は無視します。

**鍵の値をチャットやissueに貼らないこと。** 設定できているかは次で確認できます（値は表示されません）。

```bash
docker compose run --rm --entrypoint python publish -c "from automation.app import config; print(config.drive_status())"
```

## 環境変数

`.env`（git管理外、雛形は `.env.example`）。

| 変数 | 既定 | 役割 |
|---|---|---|
| `GDRIVE_FOLDER_ID` | 空 | 写真フォルダのID/URL。空なら写真なしで公開 |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/secrets/google-service-account.json` | composeが設定。通常は触らない |
| `PHOTO_ALT` | 編集部向けの既定文 | 代替テキスト。アプリは写真の中身を説明しない（見えないため） |
| `PHOTO_CREDIT` | 空 | 写真の下に出すクレジット。空なら出さない |
| `PHOTO_WIDTH` / `PHOTO_HEIGHT` / `PHOTO_QUALITY` | 1600 / 900 / 82 | 書き出しサイズと画質 |
| `PHOTO_REUSE` | `1` | 全部使い切った後に古い写真を再利用するか。`0` なら写真なしで継続 |
| `OPENAI_API_KEY` | 空 | 設定するとOpenAIが本文を書く。空なら手書き24本 |
| `OPENAI_MODEL` | `gpt-4.1-mini` | 執筆モデル |
| `LLM_MAX_TOKENS` | `2000` | 1記事あたりの出力上限 |
| `SITE_BASE_URL` | onrenderのURL | canonical・og:url・sitemap・記事URLの基点 |
| `PREVIEW_BIND` | `0.0.0.0` | `preview` の待ち受け。`127.0.0.1` で外部非公開 |
| `PUBLISH_AT` | `10:10` | scheduler が毎日動く **JST** の時刻 |
| `RUN_AT_START` | `1` | scheduler 起動直後にも1回公開するか |
| `GIT_PUSH` | `0` | `1` でコミットとpushを行う |
| `GIT_REMOTE` / `GIT_BRANCH` | `origin` / `main` | pushの宛先 |
| `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` | bot | コミットの名義 |
| `HOST_UID` / `HOST_GID` | `1000` | 生成ファイルの所有者。`id -u` / `id -g` と合わせる |
| `PREVIEW_PORT` | `8099` | preview サービスのホスト側ポート |

## git push を有効にする場合

`GIT_PUSH=1` にすると、コンテナが `data/ blog/ sitemap.xml assets/` をコミットして push します。
push にはSSH鍵がコンテナ内から見える必要があります。`docker-compose.yml` は
`SSH_DIR`（既定 `~/.ssh`）を `/ssh` として**読み取り専用**でマウントし、`SSH_KEY_FILE` で
使う鍵を選びます（このVPSでは `id_ed25519_github`）。鍵はGitHubに登録済みのものを指定してください。

```
GIT_SSH_COMMAND: ssh -i /ssh/${SSH_KEY_FILE} -o IdentitiesOnly=yes
                 -o UserKnownHostsFile=/ssh/known_hosts -o StrictHostKeyChecking=yes
```

`IdentitiesOnly` で鍵を1本に限定し、`StrictHostKeyChecking=yes` でホスト鍵を既知のものだけに
限っています。接続確認は次のとおり（鍵の中身は表示されません）。

```bash
docker compose run --rm --entrypoint sh publish -c 'ssh -i /ssh/$SSH_KEY_FILE -o IdentitiesOnly=yes -o UserKnownHostsFile=/ssh/known_hosts -T git@github.com'
```

**コンテナ内に実行UIDのユーザーが必要です。** `ssh` は `getpwuid()` でユーザーを引くため、
UIDが `/etc/passwd` に無いと `No user exists for uid 1000` でpushが失敗します。そのため
Dockerfile が `APP_UID` / `APP_GID`（composeが `HOST_UID` / `HOST_GID` から渡す）で
同じUIDのユーザーを作っています。

push先は remote `origin`（`joehisa1203-tech/yscc`）です。旧 `softrenzu/ycss` へは push しません
（push URLを無効化済み）。**Renderは旧リポジトリを見ているため、pushしても公開サイトは更新されません。**
反映したい場合はRender側の接続先切り替えが必要です（`docs/status.md` の残課題）。

## 生成物と置き場所

| パス | 内容 | git |
|---|---|---|
| `data/posts.json` | 記事データ。写真は `hero` キー | 追跡する |
| `data/photos.json` | 使用済みDrive写真の台帳（ファイルID・日付） | 追跡する |
| `assets/photos/YYYY-MM-DD-hero.jpg` | 書き出した写真 | 追跡する |
| `blog/*.html` | 記事ページ | 追跡する |
| `secrets/` | サービスアカウント鍵 | **除外** |
| `.env` | 設定値 | **除外** |

## 既知の注意点

- **公開できるのは「権利を確認した写真」だけです。** Driveに入れた時点で記事に載るので、
  クラブ公式写真や第三者の写真を無確認で入れないでください（README の運用方針と同じ）。
- `scripts/daily_blog.py` は同じ日に二重投稿しません。コンテナとGitHub Actionsの両方が動いても記事は1本です。
  ただし **公開経路を2つ動かし続けない** こと。現状の整理は `docs/status.md` を参照。
- コンテナはリポジトリをバインドマウントして直接書き込みます。`HOST_UID` を合わせないと
  root所有のファイルができ、次のローカル編集とgit操作が失敗します。
