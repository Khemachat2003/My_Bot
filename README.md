# XAUUSD Trading Bot — Phase 1: Backtest

## โครงสร้างโปรเจค

```
xauusd-bot/
├── backend/
│   ├── data_fetcher.py   ← ดึงข้อมูลราคาจาก yfinance
│   ├── indicators.py     ← RSI, MACD, EMA, BB, ATR, ADX, Stoch
│   ├── strategies.py     ← 3 strategies (EMA_RSI, RSI_MACD, BB_Breakout)
│   ├── backtest.py       ← Backtest engine + Position management
│   └── report.py         ← สร้างกราฟ + CSV report
├── data/                 ← Cache ข้อมูลราคา
├── reports/              ← ผลลัพธ์ backtest
├── run_backtest.py       ← สคริปต์หลัก ← รันตัวนี้!
└── requirements.txt
```

## วิธีติดตั้งและรัน

### 1. ติดตั้ง dependencies
```bash
pip install -r requirements.txt
```

### 2. รัน Backtest
```bash
python run_backtest.py
```

ระบบจะ:
1. ดึงข้อมูล XAUUSD (Gold Futures GC=F) จาก yfinance ย้อนหลัง 1 ปี
2. คำนวณ indicators ทั้งหมด
3. รัน 3 strategies และจำลองการเทรด
4. แสดงผล Winrate, Profit Factor, Max Drawdown
5. บันทึกกราฟ Equity Curve ที่ reports/

## 3 Strategies

| Strategy | เงื่อนไข BUY | เงื่อนไข SELL |
|---|---|---|
| EMA_RSI | EMA20>50>200, RSI 35-55, MACD hist ↑ | EMA20<50<200, RSI 45-65, MACD hist ↓ |
| RSI_MACD | RSI<32 + MACD cross up | RSI>68 + MACD cross down |
| BB_Breakout | BB squeeze แล้ว break upper | BB squeeze แล้ว break lower |

## เป้าหมาย Backtest

| Metric | เป้าหมาย | ความหมาย |
|---|---|---|
| Winrate | > 50% | ชนะมากกว่าแพ้ |
| Profit Factor | > 1.5 | กำไรรวม > ขาดทุน x1.5 |
| Max Drawdown | < 20% | ขาดทุนสูงสุดไม่เกิน 20% |
| Sharpe Ratio | > 1.0 | ผลตอบแทนดีเทียบกับความเสี่ยง |

## Phase ถัดไป

- **Phase 2**: Signal Bot + Line/Telegram Alert (FastAPI + Scheduler)
- **Phase 3**: Dashboard บน Raspberry Pi (Next.js)
- **Phase 4**: Auto Trade ผ่าน MT5 Python API (ต้องผ่าน Phase 1-2 ก่อน)

## หมายเหตุสำคัญ

> ⚠️ ระบบนี้เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่การรับประกันผลกำไร
> การเทรด Forex มีความเสี่ยงสูง ควรทดสอบด้วย Demo account ก่อนเสมอ
