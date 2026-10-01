# DEPLOY SOP — Commit → GitHub → VPS (เวอร์ชันเดียวกันทุกครั้ง)

> เอกสารนี้คือ **มาตรฐานเดียว** ของทีม — ทุกคนใช้ตามนี้ ไม่ต้องคิดเอง
> ถ้าทำตามนี้แล้ว เครื่องใคร / GitHub / VPS จะได้โค้ดเวอร์ชันเดียวกันเสมอ

---

## 0) หลักการ 4 ข้อ (จำอันนี้พอ)

1. **1 commit = 1 เวอร์ชัน** — commit คือเวอร์ชัน ไม่ใช่แค่บันทึก
2. **`main` = โปรดักชัน** — push เข้า `main` = ขึ้นของจริงทันที ห้าม push ของที่ยังพัง
3. **ห้ามแก้โค้ดบน VPS ตรง ๆ** — แก้ที่เครื่องตัวเอง → commit → push → pull บน VPS เสมอ
   (ถ้าแก้บน VPS โค้ดจะหายทั้งที่ตอน `git pull`)
4. **เช็ค hash ให้ตรงกันเสมอ** — local = GitHub = VPS ต้องได้เลขเดียวกัน (ข้อ 5)

---

## 1) Commit (บนเครื่องตัวเอง)

```bash
cd D:\Trade_Test\Trade_Phase1\xauusd-bot

git status                     # ดูว่าแก้อะไรไปบ้าง
git add backend/api.py frontend/index.html    # ✅ เพิ่มเฉพาะไฟล์ที่แก้
git commit -m "fix(api): แก้ cache ทับกราฟหลัก"
```

**ห้ามใช้ `git add -A` / `git add .`** — จะพาไฟล์ลับ (`.env`) และไฟล์ขยะขึ้นไปด้วย

### รูปแบบ commit message (ใช้ตัวนี้ทั้งทีม)

```
ประเภท(ส่วนที่แก้): อธิบายสั้น ๆ ว่าอะไรพังและแก้ยังไง
```

| ประเภท | ใช้เมื่อ |
|---|---|
| `fix(...)` | แก้บั๊ก |
| `feat(...)` | เพิ่มของใหม่ |
| `chore(...)` | งานบ้าน (deps, config) |
| `refactor(...)` | เขียนโค้ดใหม่แต่พฤติกรรมเดิม |
| `docs(...)` | เอกสาร |

ตัวอย่างจริง:

```
fix(api): candle cache ใช้ key ไม่รวม count — watchlist (count=2) แคชทับ ทำให้กราฟหลักว่าง
fix(setup_feed): re-seed buffer เมื่อ seed ตอน start ล้มเหลว — กันสัญญาณหยุดนานหลัง restart
feat(chart): เพิ่ม timeframe 15m
```

---

## 2) Push ขึ้น GitHub

```bash
git push origin main
```

ถ้าเป็นครั้งแรกของเครื่องใหม่ในทีม:

```bash
git remote -v                  # ต้องเห็น origin -> https://github.com/Khemachat2003/My_Bot.git
git fetch origin
git pull --rebase origin main  # ดึงของที่เพื่อน push มาก่อน
git push origin main
```

> **push แล้วได้อะไรต่อ?** → GitHub Actions จะ deploy ขึ้น VPS ให้เองอัตโนมัติ
> ดูผลได้ที่ **GitHub → repo → Actions → Deploy to VPS**
> ✅ เขียว = สำเร็จ · 🔴 แดง = ดู log ในนั้นเลย

---

## 3) Deploy มือ (กรณี auto-deploy ไม่ได้ / อยากคุมเอง)

```bash
ssh linuxuser@207.148.123.201
cd ~/My_Bot
git pull --ff-only origin main
docker compose up -d --build
```

**ทำไมต้อง `~/My_Bot`** — path นี้คือค่า default ของ workflow
ถ้าเครื่องคุณ clone ไว้ path อื่น (เช่น `/opt/xauusd-bot`) ให้ตั้ง secret ชื่อ **`VPS_DIR`** ให้ตรงกัน
(หรือแก้ `cd` ใน `.github/workflows/deploy.yml` บรรทัด `DEPLOY_DIR=`)

### ครั้งเดียวสำหรับคนใหม่ (setup ครั้งแรกบน VPS)

```bash
# 1) ติดตั้ง Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # แล้ว logout/login ใหม่

# 2) ดึงโค้ด
cd ~
git clone https://github.com/Khemachat2003/My_Bot.git My_Bot
cd My_Bot
cp .env.example .env
nano .env                          # ใส่ TELEGRAM_BOT_TOKEN, CHAT_ID, DASHBOARD_PASS ฯลฯ

# 3) รัน
mkdir -p data
docker compose up -d --build
```

### ครั้งเดียวสำหรับ GitHub Actions (เปิด auto-deploy)

GitHub → repo → **Settings → Secrets and variables → Actions → New repository secret**

| ชื่อ secret | ค่า |
|---|---|
| `VPS_HOST` | `207.148.123.201` |
| `VPS_USER` | `linuxuser` |
| `SSH_KEY` | private key แบบ ed25519 (ทั้งก้อน) |
| `VPS_DIR` | เว้นว่างไว้ = ใช้ `~/My_Bot` |

---

## 4) ลำดับการ deploy (สรุปสั้นที่สุด)

```
แก้โค้ดบนเครื่อง → git add → git commit → git push origin main
                                            ↓
                                   VPS: git pull --ff-only
                                            ↓
                                   docker compose up -d --build
```

---

## 5) เช็คว่าเป็นเวอร์ชันเดียวกัน (ข้อสำคัญที่สุด)

```bash
# บนเครื่องตัวเอง
git rev-parse --short HEAD

# บน VPS
cd ~/My_Bot && git rev-parse --short HEAD
```

**ต้องได้ hash เดียวกัน** เช่นทั้งคู่ได้ `9e3acf3` = sync ถูกต้อง
ถ้าไม่ตรง = มีคน push ทับ / VPS ยังไม่ pull / มีคนแก้โค้ดตรงบน VPS

ดูทั้ง 3 ที่พร้อมกัน:

```bash
git rev-parse --short HEAD && git log --oneline -3
```

---

## 6) เช็คว่าระบบยังราบรื่นหลัง deploy (4 คำสั่ง)

```bash
docker compose ps                                              # container ขึ้นไหม
curl -s -u admin:admin070717 http://127.0.0.1:8000/api/health  # API ตอบไหม
docker compose logs --tail=40 bot                              # มี error ไหม
docker stats --no-stream                                       # CPU/RAM เกินไหม
```

ผ่านเมื่อ: `ps` = `Up (healthy)` · `/api/health` คืน JSON · log ไม่มี `Traceback` · RAM < 700M

---

## 7) ย้อนกลับ (Rollback) เมื่อ deploy พัง

```bash
git log --oneline -5                    # หา hash ที่ดี (ก่อนหน้าที่พัง)
git revert <hash>                       # ✅ ปลอดภัย — ได้โค้ดเก่ามา history ไม่พัง
git push origin main
```

ทางลัด (อันตรายกว่า — history จะถูกเขียนทับ ทีมอื่นต้อง pull ใหม่):

```bash
git reset --hard <hash> && git push --force origin main
```

> ถ้า VPS เป็นปัญหา (ไม่ใช่โค้ดพัง) ให้ `git revert` เสมอ อย่า force push

---

## 8) ห้าม commit อะไร (อยู่ใน `.gitignore` แล้ว)

| ประเภท | ตัวอย่าง | ทำไม |
|---|---|---|
| ความลับ | `.env` | token/password — ห้ามขึ้น GitHub เด็ดขาด |
| ข้อมูลรัน | `data/`, `*.db` | DB ของจริง ห้ามทับ |
| ใหญ่ | `deriv_*_60s_90d.csv` | repo จะบวมจนช้า/พัง |
| เครื่องมือ | `venv/`, `__pycache__/` | สร้างใหม่ได้ |
| log | `logs/`, `reports/`, `*.log` | ไม่ต้องเก็บ |

**ก่อน commit ทุกครั้ง ให้รัน `git status` แล้วมองว่ามีอะไรแปลกปลอมไหม**
ถ้าเห็นไฟล์แปลกปลอม → อย่า `git add` มัน (ถ้าเป็นขยะ ให้ลบทิ้ง)

---

## 9) VPS เครื่องเล็ก (1 vCPU / 1GB) — ต้องรู้

ระบบรัน 5 ตัวพร้อมกัน: `api` · `setup_feed` (8 symbols) · `notifier` · `auto_retrain` · `macro_feed` (+ backup ทุก 6 ชม.)

อาการที่บอกว่า **CPU เต็ม**:

- SSH `Connection timed out` เป็นครั้งคราว
- หน้าเว็บขึ้น `ERR_CONNECTION_RESET` / กราฟไม่ขึ้น (แต่ Telegram ยังมาสัญญาณ)
- vCPU ในกราฟ Vultr พุ่ง 120–150%

ทางแก้:

```bash
docker stats --no-stream                  # ดูว่าตัวไหนกิน CPU
docker inspect -f "restarts={{.RestartCount}} OOM={{.State.OOMKilled}}" xauusd-bot
```

- **SSH เข้าไม่ได้** → ใช้ **Vultr console** (หน้าเว็บผู้ให้บริการ → View Console) แล้วรันคำสั่งข้างบน
- ลดโหลด: ลดจำนวน `TRADE_SYMBOLS` ใน `.env`, ลด `FETCH_HISTORY_COUNT`, ปิด `auto_retrain` ชั่วคราว
- อย่า `docker compose up -d --build` ซ้ำหลายรอบติด — แต่ละรอบ seed 3500 แท่ง × 8 symbols = CPU พุ่ง
- ถ้าจะรันจริงจัง → อัปเกรดเป็น 2 vCPU / 2–4GB

---

## 10) Checklist ก่อนส่งงาน (ติ๊กทีละข้อ)

- [ ] ทดสอบบนเครื่องผ่านแล้ว (ไม่ใช่แค่รันไม่ error)
- [ ] `git status` ไม่มีไฟล์แปลกปลอม
- [ ] commit message ตามรูปแบบ `ประเภท(ส่วน): อธิบาย`
- [ ] ไม่มี `.env` หรือ `data/` ติดไปด้วย
- [ ] `git push origin main` สำเร็จ
- [ ] Actions เขียว
- [ ] VPS: `git rev-parse --short HEAD` ตรงกับเครื่อง
- [ ] VPS: `docker compose ps` = healthy + `/api/health` ตอบ
