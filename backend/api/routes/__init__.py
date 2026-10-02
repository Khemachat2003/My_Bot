"""routes — APIRouter ตามกลุ่ม endpoint ของ backend.api (Phase B แยกจาก api.py แบบ move-only)

กติกา:
- ทุก route คง path/response เดิม 100% (docs/api_contract.md)
- auth ผ่าน require_auth จาก backend/api/__init__.py เท่านั้น — ห้ามย้ายไปไหน
  (tests patch DASHBOARD_USER/PASS ที่ module `backend.api` แล้ว require_auth
  อ่าน global ของ module นั้นตอน call-time)
- handler ที่อ่าน DASHBOARD_* ณ runtime ต้อง import แบบ late (ในฟังก์ชัน)
  ตาม convention เดิมของไฟล์นี้ (ดูตัวอย่าง get_cfd_paper ที่ import ในฟังก์ชัน)
"""
