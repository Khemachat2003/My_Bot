"""
report.py — สร้างรายงาน Backtest แบบ Visual
Output: backtest_report.png + backtest_trades.csv
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from backtest import BacktestResult, BacktestConfig, BacktestEngine
from indicators import add_all_indicators

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

# ─── Color Theme ─────────────────────────────────────────────────────────────
BG      = "#0d1117"
CARD    = "#161b22"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#e3b341"
BLUE    = "#58a6ff"
PURPLE  = "#bc8cff"
TEXT    = "#c9d1d9"
SUBTEXT = "#8b949e"
GRID    = "#21262d"


def generate_report(result: BacktestResult, df: pd.DataFrame,
                    output_name: str = "backtest_report") -> Path:
    fig = plt.figure(figsize=(18, 14), facecolor=BG)
    fig.suptitle("XAUUSD — Backtest Report", color=TEXT,
                 fontsize=20, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                           top=0.93, bottom=0.06)

    # ─── 1. Equity Curve (full width top) ───────────────────────────────────
    ax_equity = fig.add_subplot(gs[0, :])
    ax_equity.set_facecolor(CARD)
    ax_equity.tick_params(colors=SUBTEXT)
    for spine in ax_equity.spines.values():
        spine.set_edgecolor(GRID)

    equity = np.array(result.balance_history)
    x      = np.arange(len(equity))

    # Drawdown fill
    peak   = np.maximum.accumulate(equity)
    ax_equity.fill_between(x, equity, peak, alpha=0.2, color=RED, label="Drawdown")

    # Equity line
    color_line = GREEN if equity[-1] >= equity[0] else RED
    ax_equity.plot(x, equity, color=color_line, linewidth=1.8, label="Equity")
    ax_equity.axhline(result.config.initial_balance, color=SUBTEXT,
                       linestyle="--", linewidth=1, alpha=0.6)

    # Annotate final
    ax_equity.annotate(f"${equity[-1]:,.0f}",
                        xy=(x[-1], equity[-1]), xytext=(-60, 10),
                        textcoords="offset points", color=color_line,
                        fontsize=10, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=color_line, lw=1.2))

    ax_equity.set_title("Equity Curve", color=TEXT, fontsize=12, pad=8)
    ax_equity.set_xlabel("Candles", color=SUBTEXT, fontsize=9)
    ax_equity.set_ylabel("Balance (USD)", color=SUBTEXT, fontsize=9)
    ax_equity.legend(facecolor=CARD, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    ax_equity.yaxis.set_tick_params(labelcolor=SUBTEXT)
    ax_equity.xaxis.set_tick_params(labelcolor=SUBTEXT)
    ax_equity.grid(color=GRID, linewidth=0.5, alpha=0.5)

    # ─── 2. Metric Cards (row 1 middle 3 columns) ────────────────────────────
    metrics = [
        ("Winrate",       f"{result.winrate:.1f}%",
         GREEN if result.winrate >= 50 else RED),
        ("Profit Factor", f"{result.profit_factor:.2f}",
         GREEN if result.profit_factor >= 1.5 else (YELLOW if result.profit_factor >= 1.0 else RED)),
        ("Max Drawdown",  f"{result.max_drawdown:.1f}%",
         GREEN if result.max_drawdown < 15 else (YELLOW if result.max_drawdown < 25 else RED)),
        ("Net Profit",    f"${result.net_profit:+,.0f}",
         GREEN if result.net_profit > 0 else RED),
        ("Total Trades",  str(result.total_trades), BLUE),
        ("Sharpe Ratio",  f"{result.sharpe:.2f}",
         GREEN if result.sharpe > 1 else (YELLOW if result.sharpe > 0 else RED)),
    ]

    for idx, (label, value, color) in enumerate(metrics):
        row = 1 + idx // 3
        col = idx % 3
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor(CARD)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        for spine in ax.spines.values():
            spine.set_edgecolor(color)
            spine.set_linewidth(1.5)

        ax.text(0.5, 0.65, value, ha="center", va="center",
                color=color, fontsize=22, fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.5, 0.25, label, ha="center", va="center",
                color=SUBTEXT, fontsize=11, transform=ax.transAxes)
        # border
        rect = FancyBboxPatch((0.02, 0.05), 0.96, 0.90,
                               boxstyle="round,pad=0.02",
                               linewidth=1.5, edgecolor=color,
                               facecolor=CARD, transform=ax.transAxes)
        ax.add_patch(rect)

    # ─── 3. Win/Loss Pie ─────────────────────────────────────────────────────
    # แทนที่ metric card ตัวสุดท้ายด้วย donut chart
    ax_pie = fig.add_subplot(gs[2, 2])
    ax_pie.set_facecolor(CARD)
    wins   = result.total_wins
    losses = result.total_losses
    if wins + losses > 0:
        wedges, texts, autotexts = ax_pie.pie(
            [wins, losses],
            labels=["Win", "Loss"],
            colors=[GREEN, RED],
            autopct="%1.0f%%",
            pctdistance=0.75,
            startangle=90,
            wedgeprops={"width": 0.5, "edgecolor": BG, "linewidth": 2}
        )
        for t in texts:
            t.set_color(TEXT)
            t.set_fontsize(10)
        for at in autotexts:
            at.set_color(BG)
            at.set_fontsize(9)
            at.set_fontweight("bold")
    ax_pie.set_title("Win / Loss", color=TEXT, fontsize=11, pad=4)

    plt.savefig(REPORT_DIR / f"{output_name}.png",
                dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"[Report] บันทึกรูป → {REPORT_DIR / output_name}.png")

    # ─── Save CSV ─────────────────────────────────────────────────────────────
    trades_df = result.to_dataframe()
    if not trades_df.empty:
        csv_path = REPORT_DIR / f"{output_name}_trades.csv"
        trades_df.to_csv(csv_path, index=False)
        print(f"[Report] บันทึก trades → {csv_path}")

    plt.close()
    return REPORT_DIR / f"{output_name}.png"


if __name__ == "__main__":
    from data_fetcher import generate_synthetic_xauusd

    print("กำลังเตรียมข้อมูล...")
    df_raw = generate_synthetic_xauusd(5000, "1h")
    df     = add_all_indicators(df_raw)

    config = BacktestConfig(initial_balance=10_000, risk_per_trade_pct=1.0)
    engine = BacktestEngine(config)
    result = engine.run(df)

    print(result.summary())
    path = generate_report(result, df)
    print(f"\nรายงานบันทึกที่: {path}")
