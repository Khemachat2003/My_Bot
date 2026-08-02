# Deploy ขึ้น VPS (Ubuntu/Debian) — Vultr/Contabo

## 0) เลือก VPS

| ผู้ให้บริการ | ราคา | สเปค | หมายเหตุ |
|---|---|---|---|
| **Vultr** | $6/เดือน (แนะนำ) | 1 vCPU / 1GB RAM | ระวัง $2.50 tier มัก IPv6-only/ของจำกัด — เลือกโซน Singapore/Osaka |
| **Contabo** | ~$6-7/เดือน | 4 vCPU / 8GB RAM | ถูกสุดต่อ RAM — ถ้าอยากมีพื้นที่เหลือเยอะ |
| **Hetzner** | €4.14/เดือน | 2 vCPU / 4GB RAM | คุ้มมากถ้าโซนได้ (Singapore/Ashburn) |

**RAM ควร ≥ 1GB** เพราะรัน 3 process (pandas/sklearn) — 4GB สบายๆ และเหลือให้แอพอื่น

---

## 1) เตรียมเครื่อง

```bash
# ติดตั้ง Docker + Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # แล้ว logout/login ใหม่
docker --version                 # ทดสอบ
```

## 2) วางโค้ด

```bash
sudo mkdir -p /opt/xauusd-bot && cd /opt/xauusd-bot
sudo git clone <repo-url> .      # หรือ scp ไฟล์มา (ไม่มี git → สร้าง repo ก่อน ดูด้านล่าง)

sudo cp .env.example .env
sudo nano .env                   # ใส่ TELEGRAM_BOT_TOKEN, CHAT_ID, DASHBOARD_PASS, DERIV_SYMBOL ฯลฯ
sudo mkdir -p data               # volume สำหรับ DB (bind mount ./data)
```

## 3) รัน

```bash
docker compose up -d --build
docker compose ps                       # ดู container รันหรือยัง
docker compose logs -f --tail=50 bot    # ดู log
curl -s http://127.0.0.1:8000/api/health
```

**auto-restart:** compose มี `restart: unless-stopped` อยู่แล้ว — container crash/เครื่อง reboot เมื่อไหร่ Docker จะลุกขึ้นเองอัตโนมัติ (ไม่ต้องพึ่ง uptimerobot) พร้อมจับ SIGTERM ให้ปิด process เกลี้ยง

อัปเดตเวอร์ชันใหม่: `git pull && docker compose up -d --build`

---

## 4) Domain + HTTPS (เข้า dashboard จากมือถือ)

```bash
sudo apt install -y nginx
sudo cp deploy/nginx/xauusd.conf /etc/nginx/sites-available/xauusd
sudo nano /etc/nginx/sites-available/xauusd   # เปลี่ยน server_name เป็นโดเมนคุณ
sudo ln -s /etc/nginx/sites-available/xauusd /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d trade.yourdomain.com   # SSL ฟรี
```

> `deploy/nginx/xauusd.conf` proxy ไป `localhost:8000` อยู่แล้ว — **ไม่ต้องเปิด port 8000 สู่โลก** (firewall ปิดไว้ เปิดแค่ 80/443)

---

## 5) Security checklist (ทำก่อนเอาไปใช้งานจริง)

```bash
# 1) SSH key + ปิด password login
ssh-keygen -t ed25519                        # ฝั่ง local
ssh-copy-id <user>@<vps-ip>
# แก้ /etc/ssh/sshd_config: PasswordAuthentication no, PermitRootLogin prohibit-password
sudo systemctl restart sshd

# 2) Firewall (UFW)
sudo apt install ufw
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp        # dashboard เข้าผ่าน nginx (https) เท่านั้น
sudo ufw enable

# 3) กัน brute-force SSH
sudo apt install fail2ban

# 4) auto-update
sudo apt install unattended-upgrades

# 5) รันด้วย non-root user
sudo adduser bot && sudo usermod -aG docker bot
# เปลี่ยน /opt/xauusd-bot เจ้าของเป็น bot แล้วใช้ user bot รัน compose
```

**ความลับ:** `TELEGRAM_BOT_TOKEN` / `DASHBOARD_PASS` อยู่ใน `.env` บนเครื่องเท่านั้น — `.gitignore` กีดกันไว้แล้ว ไม่ commit ขึ้น GitHub

---

## 6) Backup (มีในตัว + ระบบ Telegram)

- ระบบ `backend/backup.py` zip `data/` (DB + models + candles) ส่งเข้า **Telegram** ทุก 6 ชม. อัตโนมัติ (`BACKUP_INTERVAL_HOURS` ใน .env)
- ไฟล์ zip เก็บที่ `data/backups/` (ปริมาณจำกัดด้วย `BACKUP_KEEP_LOCAL`)
- Backup ระดับเครื่องเพิ่มเติม (ควรทำ): cron บน VPS `rsync /opt/xauusd-bot/data/ backup:/`

---

## 7) Auto-deploy ด้วย GitHub Actions (ขั้นสูง)

ไฟล์ `.github/workflows/deploy.yml` มีให้แล้ว — push ขึ้น `main` เมื่อไหร่ deploy อัตโนมัติ:

1. `git init && git add . && git commit -m "first"` แล้ว push ขึ้น GitHub (public/private ได้)
2. ใน repo → Settings → Secrets → Actions ตั้ง:
   - `VPS_HOST` = IP/domain
   - `VPS_USER` = user (bot)
   - `SSH_KEY` = private key (paste ทั้งก้อน)
3. เตรียม `/opt/xauusd-bot/.env` ครั้งแรกตามข้อ 2
4. ต่อจากนี้ `git push` = deploy อัตโนมัติ

---

## ปัญหาที่เจอบ่อย

- **สัญญาณไม่เข้า Telegram** → เช็ค `.env` TELEGRAM_BOT_TOKEN/CHAT_ID → `docker compose logs -f bot`
- **เข้า dashboard ไม่ได้** → firewall เปิด 80/443 ไว้ไหม; nginx reload แล้วหรือยัง; เปิด https แล้วหรือยัง
- **ตลาดปิดเสาร์-อาทิตย์** → ระบบ fallback ไป R_100 อัตโนมัติ (`SYMBOL_AUTO_FALLBACK=true`)
- **container รันแต่ health ติด** → `docker compose logs bot | grep -i error`
- **อยากเทรดเฉพาะตลาดเปิด** → cron เปิด/ปิด container ตามเวลา
