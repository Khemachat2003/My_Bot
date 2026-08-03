#!/usr/bin/env bash
# firewall_allow_mobile.sh — เปิด dashboard 8000 ให้เข้าได้จากมือถือ (WiFi/4G) บน VPS
# วิธีใช้: sudo bash ~/My_Bot/deploy/firewall_allow_mobile.sh
set -u

echo "==> UFW status ก่อนแก้:"
sudo ufw status verbose

echo
echo "==> เปิดพอร์ต 8000/tcp ให้ทุก IP (dashboard มี login auth อยู่แล้ว)"
sudo ufw allow 8000/tcp comment "xauusd dashboard (mobile)"
echo "allow ok"

echo
echo "==> ยืนยัน:"
sudo ufw status verbose | grep -E "8000|Status"

echo
echo "==> เช็ค nginx reverse proxy (ถ้าใช้):"
if systemctl is-active --quiet nginx; then
  echo "nginx กำลังรัน — ดู config:"
  cat /etc/nginx/sites-enabled/xauusd.conf 2>/dev/null || cat /etc/nginx/conf.d/xauusd.conf 2>/dev/null
else
  echo "nginx ไม่รัน (ระบบน่าจะเปิด port 8000 ตรงๆ)"
fi

echo
echo "==> เช็ค docker port mapping:"
docker compose -f ~/My_Bot/docker-compose.yml ps 2>/dev/null || docker compose ps

echo
echo "==> เปิด URL จากมือถือ: http://$(hostname -I | awk '{print $1}'):8000"
echo "    (ต้องอยู่ใน WiFi เดียวกัน หรือใช้ IP สาธารณะของ VPS จากภายนอก)"
