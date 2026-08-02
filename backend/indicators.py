"""
indicators.py — คำนวณ Technical Indicators ทั้งหมด
ใช้ pandas + numpy (ไม่พึ่ง TA-Lib ที่ติดตั้งยาก)
"""
import pandas as pd
import numpy as np


# ─── Moving Averages ────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


# ─── RSI ────────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ─── MACD ───────────────────────────────────────────────────────────────────

def macd(series: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns: macd_line, signal_line, histogram"""
    fast_ema   = ema(series, fast)
    slow_ema   = ema(series, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


# ─── Bollinger Bands ────────────────────────────────────────────────────────

def bollinger_bands(series: pd.Series, period: int = 20,
                    std_dev: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns: upper, middle, lower"""
    middle = sma(series, period)
    std    = series.rolling(period).std()
    upper  = middle + std_dev * std
    lower  = middle - std_dev * std
    return upper, middle, lower


# ─── ATR ────────────────────────────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


# ─── Stochastic ─────────────────────────────────────────────────────────────

def stochastic(df: pd.DataFrame, k_period: int = 14,
               d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest  = df["low"].rolling(k_period).min()
    highest = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


# ─── ADX ────────────────────────────────────────────────────────────────────

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up   = high.diff()
    down = -low.diff()
    plus_dm  = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr_val   = atr(df, period)
    plus_di  = 100 * ema(plus_dm, period) / tr_val.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, period) / tr_val.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return ema(dx, period)


def directional_index(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series]:
    """แยก +DI / -DI ออกมาต่างหาก (adx() คำนวณข้างในแต่ไม่คืนออกมา) — ใช้บอก
    'ทิศทาง' ของเทรนด์ ต่างจาก adx เฉยๆ ที่บอกแค่ 'ความแรง' โดยไม่บอกทิศ
    """
    high, low = df["high"], df["low"]
    up   = high.diff()
    down = -low.diff()
    plus_dm  = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr_val   = atr(df, period)
    plus_di  = 100 * ema(plus_dm, period) / tr_val.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, period) / tr_val.replace(0, np.nan)
    return plus_di, minus_di


# ─── VWAP ───────────────────────────────────────────────────────────────────

def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]
    # ถ้า volume ทั้งหมดเป็น 0 หรือ NaN -> fallback ใช้ typical price (ไม่มี volume weight)
    if vol.fillna(0).sum() == 0:
        return typical
    cum_vol = vol.cumsum()
    cum_tp  = (typical * vol).cumsum()
    return cum_tp / cum_vol.replace(0, np.nan)


# ─── Support / Resistance ────────────────────────────────────────────────────

def find_pivot_highs(series: pd.Series, left: int = 5, right: int = 5) -> pd.Series:
    result = pd.Series(np.nan, index=series.index)
    for i in range(left, len(series) - right):
        window = series.iloc[i - left: i + right + 1]
        if series.iloc[i] == window.max():
            result.iloc[i] = series.iloc[i]
    return result


def find_pivot_lows(series: pd.Series, left: int = 5, right: int = 5) -> pd.Series:
    result = pd.Series(np.nan, index=series.index)
    for i in range(left, len(series) - right):
        window = series.iloc[i - left: i + right + 1]
        if series.iloc[i] == window.min():
            result.iloc[i] = series.iloc[i]
    return result


# ─── Add All Indicators to DataFrame ─────────────────────────────────────────

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    เพิ่ม indicators ทั้งหมดลงใน DataFrame
    Returns: df พร้อม columns ใหม่
    """
    df = df.copy()
    c = df["close"]

    # Moving Averages
    df["ema_20"]  = ema(c, 20)
    df["ema_50"]  = ema(c, 50)
    df["ema_200"] = ema(c, 200)
    df["sma_20"]  = sma(c, 20)

    # Momentum
    df["rsi"] = rsi(c, 14)
    df["macd_line"], df["macd_signal"], df["macd_hist"] = macd(c)

    # Volatility
    df["atr"]    = atr(df, 14)
    df["atr_pct"] = df["atr"] / c * 100  # ATR เป็น %
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(c)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100

    # Trend Strength
    df["adx"] = adx(df, 14)

    # Stochastic
    df["stoch_k"], df["stoch_d"] = stochastic(df)

    # VWAP
    df["vwap"] = vwap(df)

    # Candle properties
    df["body_size"]  = (df["close"] - df["open"]).abs() / df["open"] * 100
    df["upper_wick"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["open"] * 100
    df["lower_wick"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["open"] * 100
    df["is_bullish"] = df["close"] > df["open"]

    return df.dropna(subset=["ema_200", "rsi", "macd_line"])


if __name__ == "__main__":
    # ทดสอบ
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from data_fetcher import generate_synthetic_xauusd

    df = generate_synthetic_xauusd(1000)
    df = add_all_indicators(df)
    print(df[["close", "rsi", "macd_line", "atr", "adx", "bb_upper", "bb_lower"]].tail(5))
    print(f"\nColumns: {df.columns.tolist()}")
