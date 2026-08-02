@echo off
REM ============================================================
REM  รันระบบ live ทั้ง 3 process ด้วยคลิกเดียว
REM  (Rule-Based + ML Model + Dashboard http://localhost:8000)
REM ============================================================
cd /d "%~dp0"

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe run_live.py
) else (
    python run_live.py
)

pause
