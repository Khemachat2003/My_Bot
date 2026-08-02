@echo off
REM ============================================================
REM  ปิดระบบ live ที่รันด้วย start_live.bat อย่างนุ่มนวล
REM  (สร้างไฟล์ data\.stop_live แล้วรอ supervisor ปิดทุกตัวเอง)
REM ============================================================
cd /d "%~dp0"

if not exist data mkdir data
type nul > data\.stop_live
echo สั่งปิดแล้ว - supervisor จะปิดทุก process ภายใน 1-2 วินาที
