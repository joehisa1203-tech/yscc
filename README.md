# BLUE COURT | Y.S.C.C.横浜 JFLサッカー応援メディア

目的は、Y.S.C.C.横浜の **サッカートップチーム（JFL）** のホームゲーム観客増加と、公式のクラブ情報・スポーツ参加への導線づくりです。横浜エクセレンス向けサイトの「試合 → 観戦ガイド → チケット → 毎日ブログ」という情報設計を参考にしています。

公開サイト: https://blue-court-yscc.onrender.com/

GitHub: https://github.com/softrenzu/ycss

公式情報:

- JFL日程・結果: https://www.jfl.or.jp/jfl-pc/view/s.php?a=2591&f=2026A001_spc.html
- Y.S.C.C.横浜: https://www.yscc1986.net/
- Y.S.C.C.公式チケット: https://ticket.yscc1986.net/
- YS-BASE: https://ys-base.yscc1986.net/

## 毎日のブログ投稿

毎日の記事は、JSTの日付ごとに `scripts/daily_blog.py` が1本だけ生成します（同じ日の二重投稿はしません）。
これを動かす経路が2つあります。

- **Dockerアプリ `automation/`** … `docker compose up -d scheduler` で毎日 `PUBLISH_AT`（既定 10:10 JST）に実行。
  Google Driveのフォルダから未使用の写真を1枚取り出してヒーロー画像にし、`GIT_PUSH=1` ならcommit＆pushします。
  設計・環境変数・Driveの準備は `docs/automation.md`。
- **GitHub Actions `.github/workflows/publish.yml`** … 毎日 10:10 JST頃。写真なしのテキスト記事。
  スケジュール実行は混雑時に遅延することがあります。

**この2経路を長く併走させないでください。** どちらに寄せるかは未決で、判断材料は `docs/status.md` の残課題にあります。

Renderはmainへの変更で自動デプロイします。公開できているかは、実行ログ（Actionsの履歴、または
`docker compose logs scheduler`）とRenderのデプロイ履歴の両方で確認してください。

記事内容は、サッカー観戦の魅力・チケットの買い方・スタジアムへの行き方・JFLの見どころ・クラブへの関心を高めるテーマを24本でローテーション。架空の試合結果、観客数、チケット残席、選手のコメントや募集状況は作りません。ニュース記事の自動要約や無断転載も行いません。

写真はDriveフォルダに入れたものだけを使い、書き出し時にEXIF（GPS座標や端末情報）を取り除きます。
**フォルダに入れた写真はそのまま公開記事に載るため、権利を確認したものだけを入れてください。**

## サイト構成

- `index.html`: トップ・試合日程・チケット・初観戦ガイド・クラブ・FAQ。
- `styles.css`, `football.css`: モバイル対応の青・オレンジデザイン。
- `app.js`: 日程・記事の表示、最新ホーム戦の案内、記事カテゴリー切替。
- `data/matches.json`: 2026年11月13日に公式情報から確認したJFL日程（手動更新）。
- `data/posts.json`: ブログの記事・出典・日付。
- `blog/*.html`: SEOと共有に対応した独立記事ページ。
- `scripts/daily_blog.py`: 毎日記事生成・ページ再構築・sitemap更新。
- `automation/`: Docker版ブログ自動化アプリ（記事生成・Drive写真・commit/push・スケジューラ）とテスト。
- `docker-compose.yml`: `publish`（1回実行） / `scheduler`（毎日） / `preview`（ローカル表示確認）。
- `data/photos.json`: 使用済みDrive写真の台帳。`assets/photos/`: 書き出した写真。
- `.github/workflows/site-smoke-test.yml`: 公開先へのHTTPアクセス検証。

## 重要な運用上の注意

クラブ公式運営を装う表現は使わず、独立ファンメディアとして制作しています。公式ロゴ、写真、動画は権利確認まで転載しません。スクールの募集枠や参加条件、広告・アクセス解析連携は未設定です。

**日程は自動更新されません。** `data/matches.json` は試合の延期・中止・新日程発表に合わせて公式サイトを確認して更新してください。次のホーム戦バナーは掲載日程の範囲で自動切替し、掲載済みの最後の試合が過ぎたら非表示にして古い試合を「次回」と表示しないようにしています。

クラブの広報担当から提供される写真・募集情報・イベント告知を反映するには、提供データと使用許諾の確認が必要です。アクセス解析（GA4）や観客数実績の測定は別途設計します。

## 開発時の動作確認

Docker（推奨）:

```bash
cp .env.example .env
docker compose run --rm publish
docker compose up -d preview
```

`http://localhost:8099/` を開きます。テストは

```bash
docker compose run --rm --entrypoint python publish -m unittest discover -s automation/tests -t .
```

Dockerを使わず記事生成だけ確認する場合は `python3 scripts/daily_blog.py`（写真機能は動きません）。
