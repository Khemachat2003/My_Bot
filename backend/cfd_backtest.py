"""
cfd_backtest.py — CFD Backtest Engine
======================================
จำลองเทรด CFD โดยใช้ signal เก่า (ML + Rule-Based) + price data 1 นาที

พารามิเตอร์:
  - SL: 20 pips
  - TP1: 40 pips (R:R 1:2)
  - TP2: 60 pips (R:R 1:3)
  - Spread: 1.5 pips
  - Risk: 1% ของทุนต่อไม้
  - pip_size: 0.01 (XAUUSD)

Logic:
  สำหรับ signal เดียว จะเช็คทั้ง TP1 และ TP2 แยกกันอิสระ:
    - TP1 = ถ้าราคาไปถึง 40 pips ก่อน SL → WIN_TP1
    - TP2 = ถ้าราคาไปถึง 60 pips ก่อน SL → WIN_TP2
    - SL โดนก่อน → LOSE ทั้งคู่
    - หมดเวลา → TIMEOUT (ไม่ WIN ไม่ LOSE)

ทำให้เรารู้ว่า system เหมาะกับ R:R แบบไหนมากกว่ากัน
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "bot.db"

# ── Default CFD Parameters ────────────────────────────────────────────────────
DEFAULTS = {
    "capital": 5000.0,
    "sl_pips": 20,
    "tp1_pips": 40,
    "tp2_pips": 60,
    "spread_pips": 1.5,
    "risk_pct": 0.01,
    "max_hold_min": 60,
    "pip_size": 1.0,           # XAUUSD: 1 pip = $1.00
    "pip_value_per_lot": 100.0, # XAUUSD: $100/pip/lot (100 oz × $1.00)
}


@dataclass
class TradeResult:
    signal_id: int
    signal_type: str
    direction: str
    entry_price: float
    entry_time: str
    symbol: str
    lot_size: float
    risk_amount: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    effective_entry: float
    spread_cost: float
    tp1_result: str = "TIMEOUT"
    tp2_result: str = "TIMEOUT"
    tp1_pnl: float = 0.0
    tp2_pnl: float = 0.0
    tp1_hold_bars: int = 0
    tp2_hold_bars: int = 0


class CFDBacktest:
    def __init__(self, **kwargs):
        p = {**DEFAULTS, **kwargs}
        self.capital = p["capital"]
        self.sl_pips = p["sl_pips"]
        self.tp1_pips = p["tp1_pips"]
        self.tp2_pips = p["tp2_pips"]
        self.spread_pips = p["spread_pips"]
        self.risk_pct = p["risk_pct"]
        self.max_hold_min = p["max_hold_min"]
        self.pip_size = p["pip_size"]
        self.pip_value_per_lot = p["pip_value_per_lot"]
        self.lot_size = self._calc_lot()

    def _calc_lot(self):
        risk = self.capital * self.risk_pct
        return round(risk / (self.sl_pips * self.pip_value_per_lot), 3)

    def _connect(self):
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Fetch signals ────────────────────────────────────────────────────────
    def get_signals(self, signal_type: str = "ALL") -> list[dict]:
        conn = self._connect()
        out = []
        # check which columns exist
        setup_cols = {r["name"] for r in conn.execute("PRAGMA table_info(setup_signals)").fetchall()}
        ml_cols = {r["name"] for r in conn.execute("PRAGMA table_info(ml_signals)").fetchall()}
        has_sym = "symbol" in setup_cols

        if signal_type in ("ALL", "SETUP"):
            sym_col = "COALESCE(symbol, 'frxXAUUSD')" if has_sym else "'frxXAUUSD'"
            rows = conn.execute(f"""
                SELECT id, signal_time, entry_price, direction,
                       {sym_col} as symbol, timeframe,
                       result as binary_result, 'SETUP' as signal_type
                FROM setup_signals
                WHERE phantom = 0 AND result IN ('WIN','LOSE')
                  AND entry_price IS NOT NULL
            """).fetchall()
            out.extend(dict(r) for r in rows)
        if signal_type in ("ALL", "ML"):
            ml_has_sym = "symbol" in ml_cols
            sym_col2 = "COALESCE(symbol, 'frxXAUUSD')" if ml_has_sym else "'frxXAUUSD'"
            rows = conn.execute(f"""
                SELECT id, signal_time, entry_price, direction,
                       {sym_col2} as symbol, timeframe,
                       result as binary_result, 'ML' as signal_type
                FROM ml_signals
                WHERE phantom = 0 AND result IN ('WIN','LOSE')
                  AND entry_price IS NOT NULL
            """).fetchall()
            out.extend(dict(r) for r in rows)
        conn.close()
        return out

    # ── Fetch 1-min price candles ────────────────────────────────────────────
    def get_price_path(self, symbol: str, entry_time: str, entry_price: float,
                       max_bars: int) -> list[dict]:
        conn = self._connect()

        anchor = conn.execute("""
            SELECT ts FROM prices
            WHERE symbol = ? AND ts <= ?
            ORDER BY ts DESC LIMIT 1
        """, (symbol, entry_time)).fetchone()

        if anchor:
            start_ts = anchor["ts"]
        else:
            row_next = conn.execute("""
                SELECT ts FROM prices
                WHERE symbol = ? AND ts >= ?
                ORDER BY ts ASC LIMIT 1
            """, (symbol, entry_time)).fetchone()
            if not row_next:
                conn.close()
                return []
            start_ts = row_next["ts"]

        rows = conn.execute("""
            SELECT ts, open, high, low, close
            FROM prices
            WHERE symbol = ? AND ts >= ?
            ORDER BY ts ASC
            LIMIT ?
        """, (symbol, start_ts, max_bars + 5)).fetchall()
        conn.close()

        candles = [dict(r) for r in rows]
        if not candles:
            return []

        first_close = float(candles[0]["close"])
        pct_diff = abs(first_close - entry_price) / entry_price if entry_price else 1.0
        if pct_diff > 0.05:
            return []

        return candles

    # ── Simulate one CFD trade ──────────────────────────────────────────────
    def simulate(self, sig: dict) -> Optional[TradeResult]:
        entry = float(sig["entry_price"])
        d = sig["direction"]
        sym = sig.get("symbol") or "frxXAUUSD"
        et = sig["signal_time"]
        ps = self.pip_size

        # effective entry (spread penalty for BUY)
        spread = self.spread_pips * ps
        eff = entry + spread / 2 if d == "CALL" else entry - spread / 2

        # price targets
        if d == "CALL":
            sl  = eff - self.sl_pips * ps
            tp1 = eff + self.tp1_pips * ps
            tp2 = eff + self.tp2_pips * ps
        else:
            sl  = eff + self.sl_pips * ps
            tp1 = eff - self.tp1_pips * ps
            tp2 = eff - self.tp2_pips * ps

        candles = self.get_price_path(sym, et, entry, self.max_hold_min)
        if not candles:
            return None

        tp1_hit = tp2_hit = False
        tp1_bars = tp2_bars = 0
        sl_cost = self.sl_pips * self.pip_value_per_lot * self.lot_size
        spread_cost = self.spread_pips * self.pip_value_per_lot * self.lot_size

        for i, c in enumerate(candles):
            hi = float(c["high"])
            lo = float(c["low"])

            # SL check first (worst case)
            if d == "CALL" and lo <= sl:
                break
            if d == "PUT" and hi >= sl:
                break

            # TP1
            if not tp1_hit:
                if (d == "CALL" and hi >= tp1) or (d == "PUT" and lo <= tp1):
                    tp1_hit = True
                    tp1_bars = i + 1

            # TP2
            if not tp2_hit:
                if (d == "CALL" and hi >= tp2) or (d == "PUT" and lo <= tp2):
                    tp2_hit = True
                    tp2_bars = i + 1

            # ถ้า SL hit ในแท่งเดียวกับ TP → ถือว่า SL (worst case)
            if d == "CALL" and lo <= sl and (hi >= tp1 or hi >= tp2):
                tp1_hit = False
                tp2_hit = False
                tp1_bars = tp2_bars = 0
                break
            if d == "PUT" and hi >= sl and (lo <= tp1 or lo <= tp2):
                tp1_hit = False
                tp2_hit = False
                tp1_bars = tp2_bars = 0
                break

        risk_amt = self.sl_pips * self.pip_value_per_lot * self.lot_size

        if not tp1_hit and not tp2_hit:
            # SL or TIMEOUT → LOSE for both
            return TradeResult(
                signal_id=sig["id"],
                signal_type=sig["signal_type"],
                direction=d,
                entry_price=entry,
                entry_time=et,
                symbol=sym,
                lot_size=self.lot_size,
                risk_amount=round(risk_amt, 2),
                sl_price=round(sl, 5),
                tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5),
                effective_entry=round(eff, 5),
                spread_cost=round(spread_cost, 2),
                tp1_result="LOSE",
                tp2_result="LOSE",
                tp1_pnl=round(-risk_amt - spread_cost, 2),
                tp2_pnl=round(-risk_amt - spread_cost, 2),
            )

        tp1_pnl = 0.0
        tp2_pnl = 0.0
        tp1_res = "TIMEOUT"
        tp2_res = "TIMEOUT"

        if tp1_hit:
            tp1_pnl = (self.tp1_pips * self.pip_value_per_lot * self.lot_size) - spread_cost
            tp1_res = "WIN"
        else:
            tp1_pnl = -risk_amt - spread_cost
            tp1_res = "LOSE"

        if tp2_hit:
            tp2_pnl = (self.tp2_pips * self.pip_value_per_lot * self.lot_size) - spread_cost
            tp2_res = "WIN"
        else:
            tp2_pnl = -risk_amt - spread_cost
            tp2_res = "LOSE"

        return TradeResult(
            signal_id=sig["id"],
            signal_type=sig["signal_type"],
            direction=d,
            entry_price=entry,
            entry_time=et,
            symbol=sym,
            lot_size=self.lot_size,
            risk_amount=round(risk_amt, 2),
            sl_price=round(sl, 5),
            tp1_price=round(tp1, 5),
            tp2_price=round(tp2, 5),
            effective_entry=round(eff, 5),
            spread_cost=round(spread_cost, 2),
            tp1_result=tp1_res,
            tp2_result=tp2_res,
            tp1_pnl=round(tp1_pnl, 2),
            tp2_pnl=round(tp2_pnl, 2),
            tp1_hold_bars=tp1_bars,
            tp2_hold_bars=tp2_bars,
        )

    # ── Run full backtest ────────────────────────────────────────────────────
    def run(self, signal_type: str = "ALL") -> dict:
        signals = self.get_signals(signal_type)
        results = []
        skipped = 0
        for sig in signals:
            r = self.simulate(sig)
            if r:
                results.append(r)
            else:
                skipped += 1
        stats = self._stats(results)
        stats["skipped"] = skipped
        return stats

    # ── Aggregate statistics ─────────────────────────────────────────────────
    def _stats(self, results: list[TradeResult]) -> dict:
        s = {
            "params": {
                "capital": self.capital,
                "sl_pips": self.sl_pips,
                "tp1_pips": self.tp1_pips,
                "tp2_pips": self.tp2_pips,
                "spread_pips": self.spread_pips,
                "risk_pct": self.risk_pct,
                "lot_size": self.lot_size,
                "risk_per_trade": round(self.capital * self.risk_pct, 2),
                "pip_size": self.pip_size,
            },
            "total": len(results),
            "tp1": _blank_bucket(),
            "tp2": _blank_bucket(),
            "by_type": {},
            "by_direction": {},
            "by_type_dir": {},
            "trades": [],
        }

        for r in results:
            # TP1 bucket
            _add(s["tp1"], r.tp1_result, r.tp1_pnl)
            # TP2 bucket
            _add(s["tp2"], r.tp2_result, r.tp2_pnl)

            # by signal_type
            st = r.signal_type
            if st not in s["by_type"]:
                s["by_type"][st] = {"tp1": _blank_bucket(), "tp2": _blank_bucket()}
            _add(s["by_type"][st]["tp1"], r.tp1_result, r.tp1_pnl)
            _add(s["by_type"][st]["tp2"], r.tp2_result, r.tp2_pnl)

            # by direction
            dd = r.direction
            if dd not in s["by_direction"]:
                s["by_direction"][dd] = {"tp1": _blank_bucket(), "tp2": _blank_bucket()}
            _add(s["by_direction"][dd]["tp1"], r.tp1_result, r.tp1_pnl)
            _add(s["by_direction"][dd]["tp2"], r.tp2_result, r.tp2_pnl)

            # by type+direction
            td = f"{st}_{dd}"
            if td not in s["by_type_dir"]:
                s["by_type_dir"][td] = {"tp1": _blank_bucket(), "tp2": _blank_bucket()}
            _add(s["by_type_dir"][td]["tp1"], r.tp1_result, r.tp1_pnl)
            _add(s["by_type_dir"][td]["tp2"], r.tp2_result, r.tp2_pnl)

            # trade detail (summary only, not full to save space)
            s["trades"].append({
                "id": r.signal_id,
                "sys": r.signal_type,
                "dir": r.direction,
                "entry": r.entry_price,
                "tp1": r.tp1_result,
                "tp2": r.tp2_result,
                "pnl1": r.tp1_pnl,
                "pnl2": r.tp2_pnl,
            })

        # calculate WR for all buckets
        for bucket in [s["tp1"], s["tp2"]]:
            _calc_wr(bucket)
        for st_key in s["by_type"]:
            _calc_wr(s["by_type"][st_key]["tp1"])
            _calc_wr(s["by_type"][st_key]["tp2"])
        for d_key in s["by_direction"]:
            _calc_wr(s["by_direction"][d_key]["tp1"])
            _calc_wr(s["by_direction"][d_key]["tp2"])
        for td_key in s["by_type_dir"]:
            _calc_wr(s["by_type_dir"][td_key]["tp1"])
            _calc_wr(s["by_type_dir"][td_key]["tp2"])

        return s


def _blank_bucket() -> dict:
    return {"total": 0, "wins": 0, "losses": 0, "timeouts": 0, "pnl": 0.0, "wr": 0.0}


def _add(b: dict, result: str, pnl: float):
    b["total"] += 1
    b["pnl"] = round(b["pnl"] + pnl, 2)
    if result == "WIN":
        b["wins"] += 1
    elif result == "LOSE":
        b["losses"] += 1
    else:
        b["timeouts"] += 1


def _calc_wr(b: dict):
    if b["total"] > 0:
        b["wr"] = round(100.0 * b["wins"] / b["total"], 1)


# ── CLI runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(errors="replace")

    bt = CFDBacktest()
    print(f"CFD Backtest | Capital=${bt.capital:,.0f} | Lot={bt.lot_size} | "
          f"SL={bt.sl_pips}pip | TP1={bt.tp1_pips}pip | TP2={bt.tp2_pips}pip | "
          f"Spread={bt.spread_pips}pip | Risk={bt.risk_pct*100:.0f}%")
    print(f"Risk/Trade=${bt.capital * bt.risk_pct:.0f} | "
          f"SpreadCost=${bt.spread_pips * bt.pip_value_per_lot * bt.lot_size:.2f}")
    print("=" * 70)

    stats = bt.run("ALL")

    print(f"\nTotal signals simulated: {stats['total']} (skipped: {stats['skipped']})")

    for label, bucket in [("TP1 (R:R 1:2)", stats["tp1"]), ("TP2 (R:R 1:3)", stats["tp2"])]:
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"{'='*70}")
        print(f"  Total: {bucket['total']} | Wins: {bucket['wins']} | "
              f"Losses: {bucket['losses']} | WR: {bucket['wr']}% | "
              f"P&L: ${bucket['pnl']:+,.2f}")

        print(f"\n  By System:")
        for sys_name, sys_data in stats["by_type"].items():
            b = sys_data["tp1"] if "TP1" in label else sys_data["tp2"]
            print(f"    {sys_name:6s}: {b['total']:4d} trades | "
                  f"WR {b['wr']:5.1f}% | P&L ${b['pnl']:+8.2f}")

        print(f"\n  By Direction:")
        for dir_name, dir_data in stats["by_direction"].items():
            b = dir_data["tp1"] if "TP1" in label else dir_data["tp2"]
            print(f"    {dir_name:4s}: {b['total']:4d} trades | "
                  f"WR {b['wr']:5.1f}% | P&L ${b['pnl']:+8.2f}")

        print(f"\n  By System × Direction:")
        for td_name, td_data in stats["by_type_dir"].items():
            b = td_data["tp1"] if "TP1" in label else td_data["tp2"]
            print(f"    {td_name:12s}: {b['total']:4d} trades | "
                  f"WR {b['wr']:5.1f}% | P&L ${b['pnl']:+8.2f}")
