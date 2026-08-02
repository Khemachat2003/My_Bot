"""
run_backtest.py — สคริปต์หลักสำหรับรัน Backtest บน PC ของคุณ

วิธีใช้:
  1. pip install pandas yfinance ta numpy matplotlib
  2. python run_backtest.py

ข้อมูลจะดึงจาก yfinance (Gold Futures GC=F) อัตโนมัติ
ถ้าดึงไม่ได้จะใช้ synthetic data แทน
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from data_fetcher import get_data, generate_synthetic_xauusd
from indicators   import add_all_indicators
from backtest     import BacktestConfig, BacktestEngine
from report       import generate_report


def main():
    print("=" * 55)
    print("  XAUUSD BACKTEST SYSTEM")
    print("  Strategies: EMA_RSI | RSI_MACD | BB_BREAKOUT")
    print("=" * 55)

    # ─── โหลดข้อมูล ───────────────────────────────────────────
    print("\n[1/4] กำลังโหลดข้อมูลราคา XAUUSD...")
    try:
        df_raw = get_data("GC=F", timeframe="1h", force_refresh=True)
        print(f"      ✅ โหลดสำเร็จ {len(df_raw)} แท่งจาก yfinance")
    except Exception as e:
        print(f"      ⚠️  yfinance ไม่ได้ ({e})")
        print(f"      ⟳  ใช้ synthetic data แทน (เพื่อทดสอบ logic)")
        df_raw = generate_synthetic_xauusd(5000, "1h")

    # ─── คำนวณ Indicators ─────────────────────────────────────
    print("[2/4] คำนวณ Technical Indicators...")
    df = add_all_indicators(df_raw)
    print(f"      ✅ {len(df)} แท่ง | {df.index[0].date()} → {df.index[-1].date()}")

    # ─── Backtest Configuration ────────────────────────────────
    config = BacktestConfig(
        initial_balance    = 10000,    # เงินทุนเริ่มต้น (USD)
        risk_per_trade_pct = 5.0,       # risk 1% ต่อ trade
        spread_pips        = 3.0,       # spread 3 pips (XAUUSD)
        commission_per_lot = 7.0,       # commission $7/lot
        max_open_trades    = 1,         # เปิดทีละ 1 trade
        strategies         = ["EMA_RSI", "RSI_MACD", "BB_BREAKOUT"],
    )

    # ─── รัน Backtest ──────────────────────────────────────────
    print("[3/4] กำลัง Backtest...")
    engine = BacktestEngine(config)
    result = engine.run(df)

    # ─── แสดงผล ────────────────────────────────────────────────
    print("\n" + result.summary())

    # ─── สร้างรายงาน ───────────────────────────────────────────
    print("[4/4] สร้างรายงาน...")
    report_path = generate_report(result, df, "xauusd_backtest")

    print(f"\n✅ เสร็จสิ้น!")
    print(f"   📊 รายงาน: {report_path}")
    print(f"   📋 Trades: {report_path.parent / 'xauusd_backtest_trades.csv'}")

    # ─── คำแนะนำ ───────────────────────────────────────────────
    print("\n" + "=" * 55)
    if result.winrate >= 50 and result.profit_factor >= 1.5:
        print("  ✅ VERDICT: ผ่าน! พร้อมไปต่อ Phase 2 (Signal Bot)")
    elif result.winrate >= 45:
        print("  🟡 VERDICT: ปานกลาง — ลอง adjust parameters")
        print("  แนะนำ: เพิ่ม risk_per_trade หรือปรับ ATR multiplier")
    else:
        print("  🔴 VERDICT: ต้องปรับปรุง Strategy ก่อน")
        print("  แนะนำ: ดู trades ที่ขาดทุนใน CSV แล้ว identify pattern")
    print("=" * 55)


if __name__ == "__main__":
    main()
