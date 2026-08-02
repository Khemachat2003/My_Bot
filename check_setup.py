"""
check_setup.py — ทดสอบ setup_scorer.py กับราคาจริงจาก cache ที่มีอยู่แล้ว
(data/deriv_frxXAUUSD_60s.csv ที่ notifier.py สร้างไว้ให้ตอนรันครั้งแรก)

รัน: python check_setup.py

พิมพ์ผล checklist ของทั้ง timeframe 1 นาที และ 5 นาที (resample จาก 1m) สำหรับ
แท่งล่าสุดที่มีอยู่ในไฟล์ — เทียบกับที่พี่อ่านชาร์ตเองตอนนี้ว่าตรงกันไหม
"""
import pandas as pd

from backend.setup_scorer import score_setup

CACHE_PATH = "data/deriv_frxXAUUSD_60s.csv"


def main():
    df_1m = pd.read_csv(CACHE_PATH, index_col="datetime", parse_dates=True)
    df_1m = df_1m.sort_index()
    print(f"โหลดข้อมูลได้ {len(df_1m)} แท่ง (1 นาที) ล่าสุด: {df_1m.index[-1]}")
    print(f"ราคาปิดล่าสุด: {df_1m['close'].iloc[-1]:.2f}\n")

    # --- timeframe 1 นาที ---
    res_1m = score_setup(df_1m, timeframe="1m", target_hold_minutes=15)
    print("=" * 70)
    print(res_1m.summary_text())

    # --- timeframe 5 นาที (resample จาก 1m) ---
    df_5m = df_1m.resample("5min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna()
    res_5m = score_setup(df_5m, timeframe="5m", target_hold_minutes=25)
    print("\n" + "=" * 70)
    print(res_5m.summary_text())

    print("\n" + "=" * 70)
    print("เทียบกับที่พี่อ่านชาร์ตเองตอนนี้ตรงกันไหม? ถ้าข้อไหนดูผิดจากที่พี่มอง")
    print("ให้บอกผมว่าข้อไหน คิดว่าควรเป็นแบบไหน จะปรับเกณฑ์ให้ตรงขึ้นครับ")


if __name__ == "__main__":
    main()
