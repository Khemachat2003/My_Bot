"""conftest (root) — ทำให้ pytest import `backend.*` และ `mt5_executor` ได้จากทุกที่

pytest จะเอาโฟลเดอร์ที่มี conftest.py นี้ (root ของโปรเจกต์) ขึ้น sys.path ให้อยู่แล้ว
แต่ใส่ sys.path.insert ชัด ๆ อีกชั้นเพื่อกันกรณีรัน pytest จาก working directory อื่น
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))