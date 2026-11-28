# 管理画面と半自動公開

2026-11-28 に（同日本番反映）、毎日の記事を「自動で公開」から「自動で下書き → 管理者が公開ボタン」に変えた。
このファイルはその設計・理由・運用手順。

## 流れ

```
毎日 PUBLISH_AT（10:10 JST）   scheduler が下書きを1本作る（AIが本文、Driveから写真1枚）
        ↓                       → admin-data/drafts.json（公開されない・gitに入らない）
https://yscc.joeai.co.jp/admin/  管理者がログインして確認・編集・写真の差し替え
        ↓ 「保存して公開する」
posts.json に入る → 記事ページ・sitemap を作り直す → /var/www/yscc へ書き出し → GitHubへpush
```

| 決めたこと（2026-11-28 利用者が選択） | 内容 |
|---|---|
| 下書きの作り方 | 毎日自動で作る。管理画面の「今日の下書きを作る」でも作れる（自動実行が失敗した日用） |
| 押されなかった下書き | **下書きのまま残す。自動では公開しない。** その日はサイトの更新なし |
| 管理画面の場所 | `https://yscc.joeai.co.jp/admin/`（nginx が 127.0.0.1:8102 へ転送） |
| できること | 公開前の編集、公開済み記事の非公開化、写真の選択・差し替え・外す、AIでの書き直し |

## どこに何があるか

| 部品 | 場所 |
|---|---|
| 下書きの作成・編集・公開・非公開化 | `automation/app/drafts.py` |
| ページ再生成・書き出し・push | `automation/app/publisher.py`（`rebuild_and_ship`） |
| 記事ページのHTMLとサイトマップ | `scripts/daily_blog.py`（`build`。`generate` は Actions の検証専用） |
| 画面とログイン | `automation/admin/app.py`、`auth.py`、`templates/`、`static/admin.css` |
| 管理者アカウントの操作 | `automation/admin/users.py`（VPS上のコマンド） |
| テスト | `automation/tests/test_admin.py` |
| 下書き・パスワードハッシュ・セッション鍵 | `admin-data/`（**git管理外・公開ディレクトリ外**） |

**`data/posts.json` に入っているものが公開中の記事。** 下書きはここに入らない。

## 設計の理由

- **下書きは `admin-data/` に置き、git にも公開ディレクトリにも入れない。** リポジトリは
  公開されているので、gitに入れると未確認の記事がGitHubで読めてしまう。`export_site()` は
  許可リスト（`PUBLIC_FILES` / `PUBLIC_DIRS`）なので、`admin-data/` は書き出されない
  （`ExportSiteTest` が確認）。
- **下書きの写真も `admin-data/photos/` に置く。** `assets/` に置くと公開前に
  `https://.../assets/photos/...` で読めてしまう。公開ボタンで `assets/photos/<記事ID>-hero.jpg` へ移す。
- **写真の使用済み台帳（`data/photos.json`）は公開時に記録する。** 下書きに付けた時点で
  使用済みにすると、公開しなかった写真が二度と選ばれなくなる。非公開化したら台帳から外す。
  自動で選ぶときは、他の下書きに付いている写真も避ける。
- **禁止表現は人が書いても公開しない。** 架空の試合結果・観客数・料金・関係者コメントを
  載せない方針は、書き手がAIでも人でも同じ。判定は `writer.edit_problems()`（中身は
  `writer.BANNED`）。段落の長さなどLLMの品質管理だけは人の編集に課さない。
  保存はできるが、公開ボタンは理由を表示して止まる。
  - **正しい情報でも数字の並びは弾かれる**（例: 公式発表のスコア「2-1」、「1,000円」）。
    公式の数字を載せたい場面が出たら、`BANNED` を緩めるのではなく公式ページへのリンクで案内する。
    方針を変えるなら `CLAUDE.md` の「架空の情報を書かない」と一緒に見直すこと。
- **scheduler と管理画面は同じファイルを書くので、書き込みは必ず `drafts.lock()` の中。**
  別コンテナでも同じホストのファイルなので `flock` が効く。ロックが無いと、同時に動いたとき
  片方の変更が消える。
- **公開と push の結果は分けて表示する。** push が失敗してもサイトはもう更新されているので
  「公開失敗」と出さない。GitHubが遅れているだけなら、次の公開か「公開サイトを書き出し直す」で
  追いつく。

### ログインの守り

公開URLにログイン画面を置くので、総当たりと乗っ取りを前提にしている。

| 対策 | 実装 | 外すと |
|---|---|---|
| パスワードは scrypt ハッシュだけ保存 | `auth.set_password`（werkzeug） | 漏えい時に平文が出る |
| 12文字以上 | `auth.MIN_PASSWORD` | 短いパスワードが総当たりで破られる |
| 同じIPか同じ名前で5回失敗したら15分止める | `auth.Throttle` | 総当たりが無制限になる（`LoginTest` が落ちる） |
| フォームに使い捨てトークン（CSRF） | `app.check_csrf` | 他サイトから公開・非公開ボタンを押させられる（`LoginTest` が落ちる） |
| Cookie は `Secure` / `HttpOnly` / `SameSite=Strict` / `Path=/admin`、12時間で失効 | `create_app` | 盗まれやすくなる |
| パスワードを変えると既存のログインが無効 | `generation` 番号 | 漏れたセッションが使われ続ける |
| 枠埋め込み禁止・キャッシュ禁止・検索除外・JS不使用のCSP | `headers()`、`robots.txt` の `Disallow: /admin/` | クリックジャッキング、共有PCのキャッシュに画面が残る |

- **gunicorn は1プロセス（`-w 1`）で動かす。** 失敗回数をメモリで数えているため、
  プロセスを増やすと回数制限がプロセスごとに分かれて効かなくなる。
- **nginx は `X-Forwarded-For` を `$remote_addr` で上書きする（追記しない）。** アプリは1段だけ
  信用する（`ProxyFix(x_for=1)`）。追記にすると、送り手が書いた偽のIPで回数制限をすり抜けられる。
- ログインの成功・失敗は `docker compose logs admin` に `[ADMIN] login ...` として残る。
- Cookie の署名鍵（`admin-data/session.key`）は初回起動時にアプリが乱数で作る。値は表示しない。
  消すと全員ログアウトされるだけで、復旧作業は要らない。

## 管理者アカウント

画面からは作れない（登録画面を公開URLに置かないため）。VPS上で次を実行し、
**パスワードは本人が入力する**（表示されない入力欄。こちらで生成・代理入力はしない）。

```bash
cd /home/ubuntu/BLOG/ycss
docker compose run --rm -it --entrypoint python admin -m automation.admin.users add <名前>
docker compose run --rm -it --entrypoint python admin -m automation.admin.users passwd <名前>   # 変更
docker compose run --rm --entrypoint python admin -m automation.admin.users list
docker compose run --rm --entrypoint python admin -m automation.admin.users remove <名前>
```

## 運用

```bash
docker compose up -d admin                 # 管理画面（127.0.0.1:8102）
docker compose logs --tail=50 admin        # ログイン・公開・非公開の記録
docker compose logs --tail=50 scheduler    # 毎日の下書き作成の記録（[DRAFT] created ...）
docker compose run --rm publish            # 今日の下書きを今すぐ作る（公開はしない）
```

- コードを変えたら `docker compose build` のあと `up -d --force-recreate scheduler admin`。
  **scheduler はPythonのモジュールを起動時に読み込んだまま動き続ける**ので、作り直さないと
  古いコード（自動公開）のまま動く。
- 画面の確認は手元に https が無いので、`ADMIN_COOKIE_SECURE=0` の一時コンテナで行う
  （2026-11-28 はサンドボックスのnginx＋adminで、ログイン→下書き→写真→公開→非公開を確認した）。
- **ログイン画面は POST だけをログイン試行として数える。** GET/HEAD を数えると、死活監視の
  HEAD で失敗回数が増え、正しい利用者が締め出される（2026-11-28 反映時に発見・修正）。
- **非公開にしても GitHub の履歴には残る。** リポジトリが公開なので完全には消えない。
  画面の確認ページにも書いてある。

### nginx の設定

本番の `/etc/nginx/sites-available/yscc.joeai.co.jp` の `location / {` の前に、
`deploy/nginx/blue-court.conf.template` と同じ `location ^~ /admin/` を入れてある（2026-11-28）。
vhost を作り直すときはテンプレートと突き合わせる。
`deploy/setup_nginx.sh` はTLS設定済みのvhostを上書きしないので、本番は手で足す
（先に `/home/ubuntu/backups/` へ退避し、`sudo nginx -t && sudo systemctl reload nginx`）。

- `^~` が必要。無いと `.css` の正規表現 location が `/admin/static/admin.css` を取り、
  `/var/www/yscc` に探しに行って404になる。
- `add_header` をこの location に書かない。書くと server ブロックの `add_header`
  （X-Frame-Options 等）が継承されなくなる。
- 逆に server の `add_header` はプロキシの応答にも付くので、アプリの同名ヘッダーと二重になり値が
  食い違う（X-Frame-Options が DENY と SAMEORIGIN の2つになった。2026-11-28 反映時）。
  `proxy_hide_header` でアプリ側の X-Frame-Options / X-Content-Type-Options / Referrer-Policy を落とし、
  server の値に揃えている。枠埋め込みの禁止はアプリの CSP（`frame-ancestors 'none'`）が効く。

## 公開サイトの監視

`scripts/check_live_site.py` は「最新の記事が `CHECK_FRESH_DAYS`（既定3）日以内か」を見る。
半自動では当日の記事が無い日が普通にあるため、「当日の記事があるか」から変えた。
3日以上公開ボタンが押されていなければ落ちる（＝下書きが溜まっている合図）。
`admin-data/drafts.json` と `admin-data/users.json` が公開されていないことも確認する。

## 見送ったこと（理由ごと）

- **管理者のメール・Slack通知（「下書きができました」）は作っていない。** 要望に無く、
  送信先の設定（秘密情報）が要るため。必要になったら scheduler の `create_today()` の後に足す。
- **公開済み記事をその場で編集する機能は無い。** 非公開にして下書きで直し、再公開する。
  公開中の記事を直接書き換える経路を増やすと、確認を経ない公開が生まれるため。
- **二段階認証は入れていない。** 管理者が少数で、パスワード＋回数制限で始める。
  管理者が増えたり外部の人が使うようになったら検討する。
