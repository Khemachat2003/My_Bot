# XAUUSD Bot — production image (Python 3.11 slim)
FROM python:3.11-slim

# libgomp1 = OpenMP runtime ที่ lightgbm ต้องใช้ (image slim ไม่มี → import lightgbm
# พังตอน unpickle โมเดล = notifier ตาย = Prob Gauge/ML ว่างตลอด บน VPS)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# กัน crash เรื่อง locale/console encoding บน Linux
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=UTC \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ติดตั้ง dependency ก่อน (cache layer)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# คัดลอกโค้ด (ไม่รวม data/.venv/__pycache__ ดู .dockerignore)
COPY . .

# ข้อมูล/DB/โมเดล — เก็บเป็น volume เพื่อให้ persist เมื่อ restart
VOLUME ["/app/data"]

# port ของ api (uvicorn)
EXPOSE 8000

# ค่าเริ่มต้น: รันทั้ง 3 ระบบ (api + setup_feed + notifier) ผ่าน supervisor
# ถ้าอยากรันแค่ API (สำหรับ scale แยก) ให้ compose override command เอา
CMD ["python", "run_live.py"]
