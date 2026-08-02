"""
setup_backtest.py — Backtest ของ 🔵 Setup Scorer (9-Checklist) จริง
===================================================================================
บทบาท: backtest.py เดิมในโปรเจกต์ทดสอบ strategies.py (EMA_RSI/RSI_MACD/BB_BREAKOUT)
ซึ่งเป็นคนละระบบกับ setup_scorer.py ที่พี่ใช้เทรดจริง (9-Checklist + EMA200 Rejection)
ไฟล์นี้จำลอง "เดินเวลาไปทีละแท่ง" เหมือน setup_feed.py (ตัว live engine) ทุกประการ:

  1. เดินหน้าไปทีละแท่ง (M1 หรือ M5) ป้อนข้อมูลย้อนหลังให้ score_setup()
  2. เมื่อ entry_trigger เปลี่ยนจาก False → True (สัญญาณใหม่ ไม่ยิงซ้ำ) → บันทึก entry
  3. รอครบเวลาถือ (M1=15 นาที, M5=30 นาที) แล้วเช็คว่าราคาสุดท้ายอยู่ฝั่งไหนของ entry
     CALL ชนะถ้าราคาสูงกว่า entry, PUT ชนะถ้าราคาต่ำกว่า entry (ตรรกะเดียวกับ
     _resolve_pending_signals ใน setup_feed.py — แบบ binary option ไม่ใช่ SL/TP)

⚠️ ข้อมูลราคาที่ใช้: sandbox นี้ไม่มีอินเทอร์เน็ต ดึงราคาจริงจาก Deriv/yfinance ไม่ได้
   จึงใช้ synthetic random-walk (M1) แทนเพื่อ "เทสว่าโค้ด/ตรรกะรันได้ไม่มีบั๊ก"
   ตัวเลข winrate จากไฟล์นี้ "ใช้ตัดสินใจเรื่องเงินจริงไม่ได้" ต้องรันกับราคาจริง
   (โหลด CSV จริงจาก Deriv export หรือรันบนเครื่องพี่เองที่มีเน็ตแล้วใส่ path เข้า
   --csv) ถึงจะได้ winrate ที่มีความหมาย
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _locate_and_import_score_setup():
    """หา setup_scorer.py ให้เจอไม่ว่าไฟล์นี้จะถูกวางไว้ตรงไหนก็ตาม แล้ว import มาใช้
    ลำดับที่ค้นหา: โฟลเดอร์เดียวกับไฟล์นี้ -> ค้นทั้งโปรเจกต์ (เดิน parent ขึ้นไปสูงสุด 4 ชั้น)"""
    here = Path(__file__).resolve().parent
    candidates = [here]

    # เดินขึ้นไปหา root โปรเจกต์แล้วค้นหาทุกโฟลเดอร์ย่อย (กันกรณีวางไฟล์ผิดที่ เช่น
    # ไว้ที่ root แต่ setup_scorer.py จริงอยู่ backend\backend\)
    root = here
    for _ in range(4):
        root = root.parent
        candidates.append(root)

    found_dir = None
    for base in candidates:
        if (base / "setup_scorer.py").exists():
            found_dir = base
            break
    if found_dir is None:
        for base in candidates:
            try:
                hits = list(base.rglob("setup_scorer.py"))
            except (PermissionError, OSError):
                continue
            if hits:
                found_dir = hits[0].resolve().parent
                break

    if found_dir is None:
        print("❌ หา setup_scorer.py ไม่เจอเลยในโฟลเดอร์นี้หรือโฟลเดอร์แม่/ลูกที่เกี่ยวข้อง\n"
              "   วิธีแก้: คัดลอก setup_backtest.py ไปไว้โฟลเดอร์เดียวกับ setup_scorer.py แล้วรันจากตรงนั้น")
        sys.exit(1)

    sys.path.insert(0, str(found_dir))
    from setup_scorer import score_setup  # noqa: E402
    return score_setup


score_setup = _locate_and_import_score_setup()

MIN_BARS = 60          # ขั้นต่ำก่อนเริ่มคำนวณ (score_setup ต้องการ >= 60 แท่ง)
WINDOW = 220           # จำนวนแท่งย้อนหลังที่ป้อนให้ score_setup ต่อรอบ (กันรันช้าเกิน)
PROGRESS_EVERY = 500

TF_CONFIG = {
    "M1": {"resample_min": 1, "hold_min": 15},
    "M5": {"resample_min": 5, "hold_min": 30},
}


def generate_synthetic_1m(n_minutes: int = 20_000, seed: int = 42) -> pd.DataFrame:
    """ สร้างราคาจำลองรายนาที (ทดสอบโค้ดเท่านั้น ไม่ใช่ราคาจริง) """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.now("UTC").floor("min")
    idx = pd.date_range(end=end, periods=n_minutes, freq="1min")

    # random walk + regime เปลี่ยนแนวโน้มเป็นช่วงๆ ให้มีทั้งเทรนและ sideway
    n_regimes = 25
    regime_len = n_minutes // n_regimes
    drift = np.repeat(rng.normal(0, 0.00006, n_regimes), regime_len)
    drift = np.pad(drift, (0, n_minutes - len(drift)), mode="edge")
    noise = rng.normal(0, 0.0009, n_minutes)
    returns = drift + noise

    price = 2350.0
    closes = np.empty(n_minutes)
    for i, r in enumerate(returns):
        price *= (1 + r)
        price = min(max(price, 1800.0), 2900.0)
        closes[i] = price

    wick = rng.uniform(0.0002, 0.0015, n_minutes)
    highs = closes * (1 + wick)
    lows = closes * (1 - wick)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    volume = rng.integers(50, 500, n_minutes).astype(float)

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume},
        index=idx,
    )
    df.index.name = "datetime"
    return df


def load_csv(path: str) -> pd.DataFrame:
    """ โหลดราคาจริงจากไฟล์ CSV (คอลัมน์: datetime,open,high,low,close[,volume]) """
    df = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def resample(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        return df_1m
    rule = f"{minutes}min"
    o = df_1m["open"].resample(rule).first()
    h = df_1m["high"].resample(rule).max()
    l = df_1m["low"].resample(rule).min()
    c = df_1m["close"].resample(rule).last()
    v = df_1m["volume"].resample(rule).sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    return out.dropna()


def run_backtest_for_tf(df_1m: pd.DataFrame, tf_label: str, step: int = 1) -> pd.DataFrame:
    """ step > 1 = เช็ค checklist ทุกๆ step แท่ง แทนทุกแท่ง (เร็วขึ้น N เท่า แลกกับ
        โอกาสพลาดจังหวะ entry_trigger สั้นๆ ที่เกิด-หายระหว่าง step ที่ข้ามไป —
        ใช้ตอนอยากรันชุดข้อมูลยาวๆ ให้เร็วขึ้นสำหรับเช็คโค้ด/แนวโน้ม ไม่ใช่ผลละเอียดที่สุด) """
    cfg = TF_CONFIG[tf_label]
    df_tf = resample(df_1m, cfg["resample_min"])
    hold_bars = max(1, round(cfg["hold_min"] / cfg["resample_min"]))

    trades = []
    was_triggered = False
    n = len(df_tf)

    for i in range(MIN_BARS, n, step):
        if (i - MIN_BARS) % PROGRESS_EVERY == 0:
            print(f"  [{tf_label}] bar {i}/{n} ...", flush=True)
        window = df_tf.iloc[max(0, i - WINDOW): i + 1]
        try:
            result = score_setup(window, timeframe=tf_label, target_hold_minutes=cfg["hold_min"])
        except Exception as e:
            print(f"[{tf_label}] score_setup error @ bar {i}: {e}")
            was_triggered = False
            continue

        if result.entry_trigger and not was_triggered:
            exit_i = i + hold_bars
            if exit_i < n:  # ต้องมีข้อมูลอนาคตพอให้เช็คผล ไม่งั้นข้าม (แท่งท้ายๆ ของชุดข้อมูล)
                entry_price = df_tf["close"].iloc[i]
                exit_price = df_tf["close"].iloc[exit_i]
                direction = result.direction
                win = (exit_price > entry_price) if direction == "CALL" else (exit_price < entry_price)
                trades.append({
                    "signal_time": df_tf.index[i],
                    "direction": direction,
                    "score": result.score,
                    "entry": entry_price,
                    "exit": exit_price,
                    "result": "WIN" if win else "LOSE",
                })
        was_triggered = result.entry_trigger

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame, tf_label: str, payout: float = 0.82) -> str:
    lines = [f"\n{'='*55}", f"  SETUP SCORER BACKTEST — {tf_label}", "=" * 55]
    if trades.empty:
        lines.append("  ไม่มีสัญญาณ entry_trigger เกิดขึ้นเลยในช่วงข้อมูลนี้")
        lines.append("=" * 55)
        return "\n".join(lines)

    total = len(trades)
    wins = (trades["result"] == "WIN").sum()
    winrate = wins / total * 100
    # Binary option payout: ชนะได้ payout% ของเงินเดิมพัน, แพ้เสีย 100%
    net_units = wins * payout - (total - wins) * 1.0

    lines.append(f"  Total Signals   : {total}")
    lines.append(f"  Win / Lose      : {wins} / {total - wins}")
    lines.append(f"  Winrate         : {winrate:.1f}%")
    lines.append(f"  Payout สมมติ    : {payout*100:.0f}%  →  Net (หน่วยเดิมพัน): {net_units:+.2f}")
    breakeven_wr = 1 / (1 + payout) * 100
    lines.append(f"  Breakeven Winrate ที่ payout {payout*100:.0f}%: {breakeven_wr:.1f}%")
    lines.append("-" * 55)
    lines.append("  By direction:")
    for d, grp in trades.groupby("direction"):
        w = (grp["result"] == "WIN").sum()
        lines.append(f"    {d:5s} | {len(grp):3d} signals | WR: {w/len(grp)*100:.1f}%")
    lines.append("  By score:")
    for s, grp in trades.groupby("score"):
        w = (grp["result"] == "WIN").sum()
        lines.append(f"    score={s}/9 | {len(grp):3d} signals | WR: {w/len(grp)*100:.1f}%")
    lines.append("=" * 55)
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest ของ setup_scorer (9-Checklist) จริง")
    parser.add_argument("--csv", type=str, default=None,
                         help="path ไป CSV ราคาจริงรายนาที (datetime,open,high,low,close). "
                              "ถ้าไม่ใส่ จะใช้ synthetic data (สำหรับเทสโค้ดเท่านั้น)")
    parser.add_argument("--minutes", type=int, default=20_000,
                         help="จำนวนแท่ง 1m synthetic ที่จะสร้าง (ถ้าไม่ใส่ --csv)")
    parser.add_argument("--payout", type=float, default=0.82)
    parser.add_argument("--step", type=int, default=1,
                         help="เช็ค checklist ทุกๆ N แท่ง แทนทุกแท่ง (ช่วยให้รันข้อมูลยาวๆ เร็วขึ้น)")
    args = parser.parse_args()

    if args.csv:
        print(f"โหลดราคาจริงจาก {args.csv} ...")
        df_1m = load_csv(args.csv)
    else:
        print("⚠️  ไม่มี --csv → ใช้ synthetic random-walk data (ทดสอบโค้ดเท่านั้น ไม่ใช่ราคาจริง)")
        df_1m = generate_synthetic_1m(n_minutes=args.minutes)

    print(f"ข้อมูลทั้งหมด: {len(df_1m)} แท่ง 1m | {df_1m.index[0]} → {df_1m.index[-1]}\n")

    for tf_label in ("M1", "M5"):
        print(f"กำลังรัน backtest {tf_label} ...")
        trades = run_backtest_for_tf(df_1m, tf_label, step=args.step)
        print(summarize(trades, tf_label, payout=args.payout))
        if not trades.empty:
            out_path = Path(__file__).parent.parent / f"backtest_trades_{tf_label}.csv"
            trades.to_csv(out_path, index=False)
            print(f"  → บันทึกรายการ trade ทั้งหมดไว้ที่ {out_path}")