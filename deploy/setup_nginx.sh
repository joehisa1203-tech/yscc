#!/usr/bin/env bash
# BLUE COURT を専用ドメインで nginx 配信する。何度でも実行してよい（冪等）。
#
#   sudo bash deploy/setup_nginx.sh yscc.joeai.co.jp
#
# 2段階に分かれている。DNSがこのVPSを向く前でも 1〜3 は進むので、先に実行して
# vhost を検証しておき、DNS切り替え後にもう一度実行して証明書を取る。
# Let's Encrypt は80番を叩いて所有確認するため、TLSはDNSが向くまで取れない。
set -euo pipefail

DOMAIN="${1:?使い方: sudo bash deploy/setup_nginx.sh <ドメイン>}"
ROOT="${SITE_EXPORT_DIR:-/var/www/yscc}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VHOST="/etc/nginx/sites-available/$DOMAIN"

echo "== 1. 公開ディレクトリ =="
install -d -o "$(stat -c %u "$REPO")" -g www-data -m 0755 "$ROOT"
echo "  $ROOT"

echo "== 2. vhost =="
# certbot が追記したTLS行を消さないよう、既にTLS設定済みなら上書きしない。
if [ -f "$VHOST" ] && grep -q "listen 443" "$VHOST"; then
  echo "  $VHOST は既にTLS設定済み。上書きしない。"
else
  sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__ROOT__|$ROOT|g" \
      "$REPO/deploy/nginx/blue-court.conf.template" > "$VHOST"
  echo "  $VHOST を書き出した"
fi
ln -sfn "$VHOST" "/etc/nginx/sites-enabled/$DOMAIN"
nginx -t
systemctl reload nginx

echo "== 3. 配信の確認（DNSを介さずHostヘッダで直接叩く） =="
# reload は非同期で、古い設定がしばらく応答し続ける。待たずに叩くと他のvhostが
# 返した404を「配信できていない」と誤判定する（実際に一度やった）。
code=000
for _ in $(seq 10); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
         --resolve "$DOMAIN:80:127.0.0.1" "http://$DOMAIN/" || true)
  [ "$code" = "200" ] && break
  sleep 1
done
echo "  http://$DOMAIN/ -> $code"
[ "$code" = "200" ] || { echo "  200が返りません。$ROOT に index.html があるか確認してください。"; exit 1; }

echo "== 4. DNS の確認 =="
resolved="$(dig +short "$DOMAIN" A | head -1 || true)"
myip="$(curl -s --max-time 10 https://api.ipify.org || true)"
echo "  $DOMAIN -> ${resolved:-未解決} / このホスト -> ${myip:-不明}"
if [ "$resolved" != "$myip" ]; then
  cat <<MSG

  DNSがまだこのホストを向いていません。ここで止めます（HTTP配信の準備は完了）。
  AレコードをDNS管理画面で ${myip:-このホストのIP} に変更し、浸透後にこのコマンドを
  もう一度実行すると証明書の取得まで進みます。
MSG
  exit 0
fi

echo "== 5. TLS =="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
        --register-unsafely-without-email || {
  echo "  証明書の取得に失敗しました。HTTPのままです。certbot のログを確認してください。"
  exit 1
}
echo
echo "== 完了: https://$DOMAIN/ =="
echo "この後、.env の SITE_BASE_URL を https://$DOMAIN/ に変更し、"
echo "docker compose run --rm publish と docker compose up -d --force-recreate scheduler"
echo "を実行してください（docs/automation.md 参照）。"
