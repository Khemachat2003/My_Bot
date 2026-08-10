"""
run_live.py — รันระบบ live ทั้ง 3 process ด้วยคำสั่งเดียว
=====================================================================================
วิธีใช้:
    python run_live.py            (หรือ double-click start_live.bat)
    python run_live.py --no-api   (ไม่รัน dashboard — เทรด headless)

รัน 3 ระบบพร้อมกัน:
    🔵 backend.setup_feed   → Rule-Based 9-Checklist
    🟢 backend.notifier     → ML Model Engine
    🌐 backend.api          → Dashboard (http://localhost:8000)

คุณสมบัติ:
  - log รวมทุก process แสดงที่คอนโซลเดียว (มี tag นำหน้า)
  - ถ้า process ไหนตาย → restart อัตโนมัติ (กันหลุดข้ามคืน)
  - กด Ctrl+C ปิดทุกตัวพร้อมกัน
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ป้องกัน print ภาษาไทย/emoji แล้ว crash เมื่อ console เป็น cp1252
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

# จับ SIGTERM (docker stop / systemctl stop / kill) → ปิดทุก process เกลี้ยง
# เหมือน Ctrl+C (Windows ไม่มี SIGTERM แบบนี้ แต่มี KeyboardInterrupt ปกติ)
if os.name != "nt":
    def _on_sigterm(signum, frame):
        _print("supervisor", "รับ SIGTERM — กำลังปิดทุก process ...")
        global _stop
        _stop = True
    signal.signal(signal.SIGTERM, _on_sigterm)

MAX_RESTART = 10                 # สูงสุดกี่ครั้งต่อ process ก่อนเลิก
RESTART_WINDOW = 300             # ระยะเวลา (วินาที) ที่ใช้นับ restarts

PROCESSES = [
    {"name": "api", "cmd": ["-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"],
     "restart": True},
    {"name": "setup_feed", "cmd": ["-m", "backend.setup_feed"], "restart": True},
    {"name": "notifier", "cmd": ["-m", "backend.notifier"], "restart": True},
    # เรียนรู้จากสัญญาณจริง: ตรวจทุก N ชม. (env AUTO_RETRAIN_INTERVAL_HOURS)
    # ถ้ามีสัญญาณจริงใหม่พอ → เทรนใหม่ → ทับ model_m5 ถ้าดีกว่าโมเดลเดิม
    {"name": "auto_retrain", "cmd": ["-m", "backend.ml_forecaster.auto_retrain"],
     "restart": True},
]

BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "true").lower() not in ("0", "false", "no")

_stop = False
_ACTIVE: dict[str, subprocess.Popen] = {}
_job = None
DATA_DIR = Path(__file__).resolve().parent / "data"
SHUTDOWN_FILE = DATA_DIR / ".stop_live"


def _enable_job_kill_on_close():
    """Windows: สร้าง Job Object ที่ kill ทุก process ใน group เมื่อตัวล่าดูแลตาย
    → กัน orphan (uvicorn/setup_feed/notifier ค้าง) แม้ run_live ถูกปิดแบบแรงๆ"""
    global _job
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _job = kernel32.CreateJobObjectW(None, None)
        if not _job:
            return

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_ulonglong),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", ctypes.c_ubyte * 48),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))
        kernel32.AssignProcessToJobObject(_job, kernel32.GetCurrentProcess())
        _print("supervisor", "Job Object เปิดใช้งานแล้ว (กัน orphan process)")
    except Exception as e:
        _print("supervisor", f"⚠️ Job Object เปิดไม่สำเร็จ ({e}) — ใช้วิธี terminate ปกติแทน")


def _assign_to_job(proc):
    if os.name != "nt" or _job is None:
        return
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject(_job, ctypes.c_void_p(int(proc._handle)))
    except Exception:
        pass


def _print(name: str, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    for line in text.splitlines():
        print(f"[{ts}][{name}] {line}", flush=True)


def _pump(stream, name: str):
    try:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", errors="replace").rstrip()
            if text:
                _print(name, text)
    except Exception:
        pass


def _make_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_one(proc_cfg: dict):
    name = proc_cfg["name"]
    cmd = [sys.executable] + proc_cfg["cmd"]
    _print(name, f"กำลังสตาร์ต: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_make_env(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except Exception as e:
        _print(name, f"⚠️ ไม่สามารถสตาร์ตได้: {e}")
        return

    _ACTIVE[name] = proc
    _assign_to_job(proc)
    t = threading.Thread(target=_pump, args=(proc.stdout, name), daemon=True)
    t.start()

    try:
        rc = proc.wait()
    except KeyboardInterrupt:
        _terminate(proc)
        return
    finally:
        _ACTIVE.pop(name, None)
    _print(name, f"process ออกด้วยรหัส {rc}")


def _terminate(proc):
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        pass
    if proc.poll() is None:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
    # fallback สุดท้ายสำหรับ Windows: ฆ่าต้นไม้ process ฟันธง
    if os.name == "nt" and proc.poll() is None:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def _stop_all():
    """ปิดทุก child process (กัน orphan ค้างไว้)"""
    for name, proc in list(_ACTIVE.items()):
        _print("supervisor", f"ปิด {name} ...")
        _terminate(proc)


def _start_backup_thread(stop_event):
    """เปิด thread backup ข้อมูลอัตโนมัติ (ถ้าเปิดใช้ใน .env)"""
    if not BACKUP_ENABLED:
        _print("backup", "BACKUP_ENABLED=false — ข้ามการสำรองข้อมูล")
        return None
    try:
        from backend.backup import backup_loop
        t = threading.Thread(target=backup_loop, args=(stop_event,), daemon=True)
        t.start()
        _print("backup", "thread สำรองข้อมูลเริ่มทำงานแล้ว (ทุก 6 ชม. + ตอนเปิดระบบ)")
        return t
    except Exception as e:
        _print("backup", f"⚠️ เปิด thread backup ไม่สำเร็จ: {e}")
        return None


def main():
    global _stop
    use_api = "--no-api" not in sys.argv
    cfgs = [c for c in PROCESSES if c["name"] != "api" or use_api]

    _enable_job_kill_on_close()
    _print("supervisor", f"รัน {len(cfgs)} ระบบพร้อมกัน (Ctrl+C หรือสร้างไฟล์ data/.stop_live เพื่อปิด)")

    # ล้างไฟล์สั่งปิดเก่า (ถ้ามีจากครั้งก่อน)
    try:
        SHUTDOWN_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    for c in cfgs:
        _print("supervisor", f"  → {c['name']}: python {' '.join(c['cmd'])}")

    threads = []
    for cfg in cfgs:
        t = threading.Thread(target=_supervise, args=(cfg,), daemon=True)
        t.start()
        threads.append(t)

    stop_event = threading.Event()
    _start_backup_thread(stop_event)

    try:
        while True:
            time.sleep(1)
            if _stop:
                _stop_all()
                stop_event.set()
                return
            if SHUTDOWN_FILE.exists():
                _print("supervisor", "พบไฟล์สั่งปิด data/.stop_live — กำลังปิดทุก process ...")
                _stop = True
                try:
                    SHUTDOWN_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                _stop_all()
                stop_event.set()
                return
    except KeyboardInterrupt:
        _stop = True
        _print("supervisor", "รับ Ctrl+C — กำลังปิดทุก process ...")
        _stop_all()
        time.sleep(1)
        stop_event.set()


def _supervise(cfg: dict):
    name = cfg["name"]
    restarts = []
    attempts = 0
    while not _stop:
        if cfg["restart"]:
            now = time.time()
            restarts = [t for t in restarts if now - t < RESTART_WINDOW]
            if len(restarts) >= MAX_RESTART:
                _print(name, f"❌ restarted เกิน {MAX_RESTART} ครั้งใน {RESTART_WINDOW}s — หยุดติดตาม")
                return
        _run_one(cfg)
        if _stop:
            return
        attempts += 1
        restarts.append(time.time())
        delay = min(5 * attempts, 30)
        _print(name, f"จะ restart ใหม่ใน {delay} วินาที ...")
        for _ in range(delay):
            if _stop:
                return
            time.sleep(1)


if __name__ == "__main__":
    main()
