"""
data_fetcher.py — ดึงข้อมูล XAUUSD ย้อนหลัง
รองรับ: yfinance (GC=F), CSV fallback
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import time

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

TIMEFRAME_MAP = {
    "15m": ("15m", 60),    # interval, days_back
    "1h":  ("1h",  365),
    "4h":  ("4h",  730),
    "1d":  ("1d",  1095),
}


def fetch_yfinance(symbol: str = "GC=F", timeframe: str = "1h", days_back: int = 365) -> pd.DataFrame:
    """
    ดึงข้อมูลจาก yfinance
    GC=F = Gold Futures (XAUUSD ใกล้เคียงที่สุด)
    """
    import yfinance as yf

    end   = datetime.now()
    start = end - timedelta(days=days_back)

    tf_map = {"15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}
    interval = tf_map.get(timeframe, "1h")

    print(f"[DataFetcher] ดึงข้อมูล {symbol} | TF:{timeframe} | {start.date()} → {end.date()}")
    df = yf.download(symbol, start=start, end=end, interval=interval,
                     auto_adjust=True, progress=False)

    if df.empty:
        raise ValueError(f"ไม่สามารถดึงข้อมูล {symbol} ได้")

    # Flatten multi-index columns ถ้ามี
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df.index.name = "datetime"
    df = df[["open", "high", "low", "close", "volume"]].dropna()

    # Resample เป็น 4H ถ้าต้องการ
    if timeframe == "4h":
        df = df.resample("4h").agg({
            "open": "first", "high": "max",
            "low": "min", "close": "last", "volume": "sum"
        }).dropna()

    # Cache ลง disk
    cache_path = DATA_DIR / f"{symbol.replace('=','_')}_{timeframe}.csv"
    df.to_csv(cache_path)
    print(f"[DataFetcher] บันทึก cache → {cache_path} ({len(df)} แท่ง)")
    return df


def load_cached(symbol: str = "GC=F", timeframe: str = "1h") -> pd.DataFrame | None:
    """โหลดจาก cache ถ้ามี"""
    cache_path = DATA_DIR / f"{symbol.replace('=','_')}_{timeframe}.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col="datetime", parse_dates=True)
        print(f"[DataFetcher] โหลด cache {cache_path} ({len(df)} แท่ง)")
        return df
    return None


def get_data(symbol: str = "GC=F", timeframe: str = "1h",
             force_refresh: bool = False) -> pd.DataFrame:
    """
    Entry point หลัก — ลอง cache ก่อน ถ้าไม่มีค่อย fetch ใหม่
    """
    if not force_refresh:
        cached = load_cached(symbol, timeframe)
        if cached is not None and len(cached) > 100:
            return cached

    _, days_back = TIMEFRAME_MAP.get(timeframe, ("1h", 365))
    return fetch_yfinance(symbol, timeframe, days_back)


def generate_synthetic_xauusd(n_candles: int = 5000, timeframe: str = "1h") -> pd.DataFrame:
    """
    สร้างข้อมูลจำลอง XAUUSD สำหรับ dev/test
    ราคาอิงจาก random walk ช่วง $1800-$2500
    """
    np.random.seed(42)
    freq_map = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
    freq = freq_map.get(timeframe, "1h")

    end   = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=n_candles)
    dates = pd.date_range(start=start, end=end, freq=freq)[:n_candles]

    # Simulate realistic gold price movement
    returns = np.random.normal(0.0001, 0.008, n_candles)

    # เพิ่ม trend และ seasonality
    trend = np.linspace(0, 0.3, n_candles)
    cycle = 0.05 * np.sin(np.linspace(0, 8 * np.pi, n_candles))
    returns = returns + trend / n_candles + cycle / n_candles

    price = 1900.0
    closes = [price]
    for r in returns[1:]:
        price = price * (1 + r)
        price = max(1700, min(2600, price))
        closes.append(price)

    closes = np.array(closes)
    noise  = np.random.uniform(0.001, 0.006, n_candles)

    highs   = closes * (1 + noise)
    lows    = closes * (1 - noise)
    opens   = np.roll(closes, 1)
    opens[0] = closes[0]
    volumes = np.random.randint(1000, 50000, n_candles).astype(float)

    df = pd.DataFrame({
        "open": opens, "high": highs,
        "low": lows,   "close": closes, "volume": volumes
    }, index=dates)
    df.index.name = "datetime"
    print(f"[DataFetcher] สร้าง synthetic data {len(df)} แท่ง | {df.index[0]} → {df.index[-1]}")
    return df


if __name__ == "__main__":
    # ทดสอบ
    df = generate_synthetic_xauusd(3000, "1h")
    print(df.tail())
    print(f"\nราคาล่าสุด: ${df['close'].iloc[-1]:.2f}")
