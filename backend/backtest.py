"""
backtest.py — Backtest Engine สำหรับ XAUUSD
Features:
  - Simulate trade execution (market order)
  - Position management (SL / TP1 / TP2)
  - Partial close ที่ TP1 (50%) แล้ว move SL to breakeven
  - Commission + Spread simulation
  - รายงาน Winrate, Profit Factor, Max Drawdown, Sharpe
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from indicators import add_all_indicators
from strategies import get_signal, Signal


# ─── Config ──────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    initial_balance:    float = 10_000.0   # USD
    risk_per_trade_pct: float = 1.0        # % ของ balance ต่อ trade
    spread_pips:        float = 3.0        # spread (points สำหรับ XAUUSD)
    commission_per_lot: float = 7.0        # USD ต่อ lot (round trip)
    min_lot:            float = 0.01
    max_lot:            float = 10.0
    lot_step:           float = 0.01
    tp1_partial_close:  float = 0.5        # ปิด 50% ที่ TP1
    strategies:         list  = field(default_factory=lambda: ["EMA_RSI", "RSI_MACD", "BB_BREAKOUT"])
    max_open_trades:    int   = 1          # เปิด trade พร้อมกันได้กี่ positions
    symbol:             str   = "XAUUSD"
    pip_value:          float = 1.0        # USD ต่อ 1 pip ต่อ 0.01 lot (XAUUSD = $0.01/pip/0.01lot → $1/pip/lot)


# ─── Trade Record ────────────────────────────────────────────────────────────

@dataclass
class Trade:
    id:         int
    open_time:  pd.Timestamp
    direction:  str     # BUY / SELL
    entry:      float
    sl:         float
    tp1:        float
    tp2:        float
    lot:        float
    strategy:   str
    reason:     str
    atr:        float

    close_time: Optional[pd.Timestamp] = None
    close_price:float = 0.0
    profit:     float = 0.0
    status:     str   = "OPEN"   # OPEN / WIN_TP1 / WIN_TP2 / LOSS_SL / CLOSED
    closed_partial: bool = False  # ปิด TP1 ไปแล้ว
    sl_moved:       bool = False  # เลื่อน SL to BE แล้ว


# ─── Lot Size Calculator ─────────────────────────────────────────────────────

def calculate_lot(balance: float, risk_pct: float, entry: float,
                  sl: float, config: BacktestConfig) -> float:
    """
    คำนวณ lot size จาก % risk
    XAUUSD: pip_value = $1 per pip per lot
    1 pip = $0.1 (0.1 USD per 0.01 lot per pip)
    """
    risk_amount = balance * (risk_pct / 100)
    sl_pips     = abs(entry - sl) * 10  # XAUUSD 1 point = 0.1 pip convention
    if sl_pips == 0:
        return config.min_lot

    lot = risk_amount / (sl_pips * config.pip_value * 100)
    lot = round(lot / config.lot_step) * config.lot_step
    lot = max(config.min_lot, min(config.max_lot, lot))
    return lot


# ─── Backtest Engine ─────────────────────────────────────────────────────────

class BacktestEngine:
    def __init__(self, config: BacktestConfig = None):
        self.config  = config or BacktestConfig()
        self.trades: list[Trade] = []
        self.balance_history: list[float] = []
        self.balance = self.config.initial_balance
        self.equity  = self.config.initial_balance
        self.trade_counter = 0
        self.open_trades: list[Trade] = []

    def _spread_adjusted_entry(self, price: float, direction: str) -> float:
        spread = self.config.spread_pips * 0.1  # convert pips to price
        return price + spread if direction == "BUY" else price - spread

    def _calc_profit(self, trade: Trade, close_price: float,
                     lot_multiplier: float = 1.0) -> float:
        lot     = trade.lot * lot_multiplier
        points  = close_price - trade.entry if trade.direction == "BUY" \
                  else trade.entry - close_price
        profit  = points * lot * 100  # XAUUSD: $100 per point per lot (approx)
        commission = self.config.commission_per_lot * lot
        return profit - commission

    def _open_trade(self, time: pd.Timestamp, signal: Signal) -> Trade:
        self.trade_counter += 1
        entry = self._spread_adjusted_entry(signal.entry, signal.direction)
        lot   = calculate_lot(self.balance, self.config.risk_per_trade_pct,
                               entry, signal.sl, self.config)
        trade = Trade(
            id=self.trade_counter, open_time=time,
            direction=signal.direction, entry=entry,
            sl=signal.sl, tp1=signal.tp1, tp2=signal.tp2,
            lot=lot, strategy=signal.strategy,
            reason=signal.reason, atr=signal.atr
        )
        self.open_trades.append(trade)
        return trade

    def _update_open_trades(self, candle: pd.Series) -> None:
        high, low = candle["high"], candle["low"]
        to_remove = []

        for trade in self.open_trades:
            # Move SL to breakeven after TP1 hit
            if trade.closed_partial and not trade.sl_moved:
                trade.sl      = trade.entry
                trade.sl_moved = True

            if trade.direction == "BUY":
                # SL hit
                if low <= trade.sl:
                    pnl = self._calc_profit(trade, trade.sl,
                                             0.5 if trade.closed_partial else 1.0)
                    trade.profit     += pnl
                    trade.close_price = trade.sl
                    trade.close_time  = candle.name
                    trade.status      = "LOSS_SL" if not trade.closed_partial else "WIN_TP1"
                    self.balance     += trade.profit
                    to_remove.append(trade)

                # TP1 hit (partial close)
                elif high >= trade.tp1 and not trade.closed_partial:
                    pnl = self._calc_profit(trade, trade.tp1, self.config.tp1_partial_close)
                    trade.profit        += pnl
                    trade.closed_partial = True
                    self.balance        += pnl

                # TP2 hit
                elif high >= trade.tp2:
                    remaining = 0.5 if trade.closed_partial else 1.0
                    pnl = self._calc_profit(trade, trade.tp2, remaining)
                    trade.profit     += pnl
                    trade.close_price = trade.tp2
                    trade.close_time  = candle.name
                    trade.status      = "WIN_TP2"
                    self.balance     += pnl
                    to_remove.append(trade)

            else:  # SELL
                if high >= trade.sl:
                    pnl = self._calc_profit(trade, trade.sl,
                                             0.5 if trade.closed_partial else 1.0)
                    trade.profit     += pnl
                    trade.close_price = trade.sl
                    trade.close_time  = candle.name
                    trade.status      = "LOSS_SL" if not trade.closed_partial else "WIN_TP1"
                    self.balance     += trade.profit
                    to_remove.append(trade)

                elif low <= trade.tp1 and not trade.closed_partial:
                    pnl = self._calc_profit(trade, trade.tp1, self.config.tp1_partial_close)
                    trade.profit        += pnl
                    trade.closed_partial = True
                    self.balance        += pnl

                elif low <= trade.tp2:
                    remaining = 0.5 if trade.closed_partial else 1.0
                    pnl = self._calc_profit(trade, trade.tp2, remaining)
                    trade.profit     += pnl
                    trade.close_price = trade.tp2
                    trade.close_time  = candle.name
                    trade.status      = "WIN_TP2"
                    self.balance     += pnl
                    to_remove.append(trade)

        for t in to_remove:
            self.trades.append(t)
            self.open_trades.remove(t)

    def run(self, df: pd.DataFrame) -> "BacktestResult":
        self.balance = self.config.initial_balance
        self.trades  = []
        self.open_trades = []
        self.balance_history = [self.balance]

        df = df.copy().reset_index()
        df_indexed = df.set_index("datetime")

        for i in range(1, len(df)):
            row  = df_indexed.iloc[i]
            prev = df_indexed.iloc[i - 1]

            # อัปเดต open trades ก่อน
            self._update_open_trades(row)

            # เช็ค signal สำหรับ trade ใหม่
            if len(self.open_trades) < self.config.max_open_trades:
                signal = get_signal(row, prev, self.config.strategies)
                if signal.direction != "NONE":
                    self._open_trade(row.name, signal)

            self.balance_history.append(self.balance)

        # Force close เทรดที่ค้างอยู่
        if self.open_trades:
            last_row = df_indexed.iloc[-1]
            for trade in self.open_trades:
                remaining = 0.5 if trade.closed_partial else 1.0
                pnl = self._calc_profit(trade, last_row["close"], remaining)
                trade.profit     += pnl
                trade.close_price = last_row["close"]
                trade.close_time  = last_row.name
                trade.status      = "CLOSED"
                self.balance     += pnl
                self.trades.append(trade)
            self.open_trades = []

        return BacktestResult(self.trades, self.balance_history, self.config)


# ─── Result Analysis ──────────────────────────────────────────────────────────

class BacktestResult:
    def __init__(self, trades: list[Trade], balance_history: list[float],
                 config: BacktestConfig):
        self.trades          = trades
        self.balance_history = balance_history
        self.config          = config
        self._compute_metrics()

    def _compute_metrics(self):
        closed = [t for t in self.trades if t.status != "OPEN"]
        self.total_trades = len(closed)

        if self.total_trades == 0:
            self.winrate = self.profit_factor = self.max_drawdown = 0
            self.net_profit = self.expectancy = self.sharpe = 0
            return

        wins   = [t for t in closed if t.profit > 0]
        losses = [t for t in closed if t.profit <= 0]

        self.total_wins   = len(wins)
        self.total_losses = len(losses)
        self.winrate      = self.total_wins / self.total_trades * 100

        gross_profit = sum(t.profit for t in wins)
        gross_loss   = abs(sum(t.profit for t in losses))
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        self.net_profit    = gross_profit - gross_loss
        self.expectancy    = self.net_profit / self.total_trades

        # Max Drawdown
        equity = np.array(self.balance_history)
        peak   = np.maximum.accumulate(equity)
        dd     = (equity - peak) / peak * 100
        self.max_drawdown  = abs(dd.min())
        self.final_balance = equity[-1]
        self.total_return  = (self.final_balance - self.config.initial_balance) / \
                              self.config.initial_balance * 100

        # Sharpe Ratio (simplified daily)
        returns = pd.Series(self.balance_history).pct_change().dropna()
        self.sharpe = (returns.mean() / returns.std() * np.sqrt(252)) \
                       if returns.std() > 0 else 0

        # By strategy
        self.by_strategy = {}
        all_strategies = set(t.strategy for t in closed)
        for strat in all_strategies:
            st = [t for t in closed if t.strategy == strat]
            sw = [t for t in st if t.profit > 0]
            self.by_strategy[strat] = {
                "trades": len(st),
                "wins":   len(sw),
                "winrate": len(sw) / len(st) * 100 if st else 0,
                "net_profit": sum(t.profit for t in st),
            }

    def summary(self) -> str:
        lines = [
            "=" * 55,
            f"  BACKTEST RESULTS — {self.config.symbol}",
            "=" * 55,
            f"  Initial Balance : ${self.config.initial_balance:,.2f}",
            f"  Final Balance   : ${self.final_balance:,.2f}",
            f"  Net Profit      : ${self.net_profit:,.2f}  ({self.total_return:.1f}%)",
            "-" * 55,
            f"  Total Trades    : {self.total_trades}",
            f"  Win / Loss      : {self.total_wins} / {self.total_losses}",
            f"  Winrate         : {self.winrate:.1f}%",
            f"  Profit Factor   : {self.profit_factor:.2f}",
            f"  Expectancy      : ${self.expectancy:.2f}/trade",
            f"  Max Drawdown    : {self.max_drawdown:.1f}%",
            f"  Sharpe Ratio    : {self.sharpe:.2f}",
            "-" * 55,
            "  BY STRATEGY:",
        ]
        for s, m in self.by_strategy.items():
            lines.append(f"  {s:15s} | {m['trades']:3d} trades | "
                         f"WR:{m['winrate']:.0f}% | "
                         f"P/L:${m['net_profit']:+.0f}")
        lines.append("=" * 55)

        # Grade
        grade = "🔴 ต้องปรับปรุง"
        if self.winrate >= 50 and self.profit_factor >= 1.5 and self.max_drawdown < 20:
            grade = "🟢 พร้อมใช้งาน (Phase 2)"
        elif self.winrate >= 45 and self.profit_factor >= 1.2:
            grade = "🟡 ปานกลาง (ปรับ parameter)"

        lines.append(f"\n  VERDICT: {grade}")
        lines.append(f"  Risk per trade: {self.config.risk_per_trade_pct}%")
        lines.append("=" * 55)
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([{
            "id": t.id, "strategy": t.strategy,
            "open_time": t.open_time, "close_time": t.close_time,
            "direction": t.direction, "entry": t.entry,
            "close_price": t.close_price, "sl": t.sl,
            "tp1": t.tp1, "tp2": t.tp2,
            "lot": t.lot, "profit": t.profit,
            "status": t.status, "reason": t.reason,
        } for t in self.trades])


# ─── Main Runner ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from data_fetcher import generate_synthetic_xauusd

    print("กำลังโหลดข้อมูล XAUUSD...")
    df_raw = generate_synthetic_xauusd(n_candles=5000, timeframe="1h")

    print("คำนวณ indicators...")
    df = add_all_indicators(df_raw)

    print(f"ข้อมูลที่ใช้ backtest: {len(df)} แท่งเทียน")
    print(f"ช่วงเวลา: {df.index[0]} → {df.index[-1]}\n")

    config = BacktestConfig(
        initial_balance=10_000,
        risk_per_trade_pct=1.0,
        spread_pips=3.0,
        commission_per_lot=7.0,
    )

    engine = BacktestEngine(config)
    print("Running backtest...")
    result = engine.run(df)
    print(result.summary())

    trades_df = result.to_dataframe()
    if not trades_df.empty:
        print(f"\nตัวอย่าง trades ล่าสุด:")
        print(trades_df[["strategy","direction","entry","close_price","profit","status"]].tail(10).to_string(index=False))
