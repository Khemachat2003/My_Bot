"""schemas.py — pydantic Body models ของ backend.api (schema กลางของ request body)

Phase B: ย้ายมาจาก backend/api.py แบบ move-only — แยกไฟล์เพื่อให้ทุก route
อ้าง model ชุดเดียวกัน และเตรียมเผยผ่าน /openapi.json (ใช้ auth) เพื่อ gen TS types
ให้ฝั่ง frontend ต่อ (ดู docs/api_contract.md)
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginBody(BaseModel):
    username: str
    password: str


class JournalSettingsBody(BaseModel):
    capital: float
    stake: float
    currency: str = "THB"
