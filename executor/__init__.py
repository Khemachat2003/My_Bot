"""executor — MT5 order executor (Windows) ที่รันแยกจากระบบหลักบน VPS

mt5_executor.py ดึงสัญญาณ FIRE จาก API ของ VPS แล้วส่งออเดอร์ MT5 จริง
พร้อม SL/TP — ตั้งค่าผ่าน .env (MT5_* variables ดู .env.example)
"""