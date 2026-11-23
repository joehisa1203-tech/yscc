#!/usr/bin/env bash
# BLUE COURT を nginx で公開する。DNSがこのVPSを向いた後に実行する。
#   sudo bash deploy/setup_nginx.sh blue-court.joeai.co.jp
# 証明書の取得にはDNSが解決していることが必要（Let's Encryptが80番を叩く）。
set -euo pipefail

DOMAIN="${1:?使い方: sudo bash deploy/setup_nginx.sh <ドメイン>}"
ROOT="${SITE_EXPORT_DIR:-/var/www/blue-court}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== 1. DNSの確認 =="
resolved="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
myip="$(curl -s --max-time 10 https://api.ipify.org || true)"
echo "  $DOMAIN -> ${resolved:-未解決} / このホスト -> ${myip:-不明}"
if [ "$resolved" != "$myip" ]; then
  echo "  DNSがこのホストを向いていません。Aレコードを $myip にしてから再実行してください。"
  exit 1
fi

echo "== 2. 公開ディレクトリ =="
install -d -o "$(stat -c %u "$REPO")" -g www-data -m 0755 "$ROOT"
echo "  $ROOT"

echo "== 3. vhost =="
sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__ROOT__|$ROOT|g" \
    "$REPO/deploy/nginx/blue-court.conf.template" > "/etc/nginx/sites-available/blue-court"
ln -sfn /etc/nginx/sites-available/blue-court /etc/nginx/sites-enabled/blue-court
nginx -t
systemctl reload nginx
echo "  http://$DOMAIN/ で配信開始"

echo "== 4. TLS =="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
        --register-unsafely-without-email || {
  echo "  証明書の取得に失敗しました。HTTPのままです。certbot のログを確認してください。"
  exit 1
}
echo "== 完了: https://$DOMAIN/ =="
echo "この後、.env の SITE_EXPORT_DIR と SITE_BASE_URL を設定して"
echo "docker compose restart scheduler を実行してください（docs/automation.md 参照）。"
