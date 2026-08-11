"""
features_v2.py — Phase 3: feature ใหม่เฉพาะ short-horizon (1-5-15 นาที)

ต่อยอดจาก features.py เดิม (ไม่แก้ของเดิม เผื่อต้องเทียบ A/B กัน) เพิ่ม 4 กลุ่ม
ตามที่ระบุไว้ใน PROJECT_HANDOFF.md ข้อ 1-3 + Mean Reversion สำหรับ Option:

  1. Multi-timeframe context (mtf5_*, mtf15_*)
     — indicator บนแท่ง 5 นาที/15 นาที สะท้อน "เทรนด์ใหญ่" ให้โมเดล 1 นาทีเห็น
  2. Microstructure / price-action (streak, accel, realized vol, range)
     — พฤติกรรมราคาระยะสั้นมากที่ indicator มาตรฐานจับไม่ได้
  3. Session dummies แบบละเอียด (แทน hour_sin/cos เดียว)
     — Asian / London / NY / London-NY overlap แยกเป็น flag เพื่อให้โมเดล
       เรียนรู้ pattern เฉพาะ session ได้ตรงกว่า cyclical encoding เดียว
  4. Mean Reversion / Reversal (สำคัญสำหรับ Option ระยะสั้น)
     — RSI extreme, BB squeeze, price-vs-VWAP distance, volume spike,
       candle rejection (wick/body ratio), momentum divergence proxy

**สำคัญ (กัน lookahead bias):** multi-timeframe resample ใช้
`label="right", closed="right"` แล้ว merge_asof แบบ `direction="backward"`
กลับเข้าแท่ง 1 นาที — หมายความว่า ณ เวลา t ใดๆ โมเดลเห็นได้แค่แท่ง HTF
ที่ "ปิดสนิทแล้ว" เท่านั้น ไม่มีการแอบดูข้อมูลอนาคตของแท่งใหญ่ที่ยังไม่ปิด
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.indicators import ema, rsi, macd, atr, bollinger_bands, stochastic, vwap
from backend.ml_forecaster.features import build_features, FEATURE_COLUMNS as FEATURE_COLUMNS_V1


# ─── 1. Multi-timeframe context ──────────────────────────────────────────────

def _htf_block(df: pd.DataFrame, timeframe: str, prefix: str) -> pd.DataFrame:
    """สร้าง indicator บน timeframe ใหญ่กว่า (เช่น '5min', '15min')
    label/closed='right' = timestamp ของแท่งคือเวลาที่แท่งนั้น "ปิด" แล้ว
    """
    ohlc = (
        df[["open", "high", "low", "close"]]
        .resample(timeframe, label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    c = ohlc["close"]
    ema_fast, ema_slow = ema(c, 9), ema(c, 21)
    _, _, macd_hist = macd(c)

    htf = pd.DataFrame(index=ohlc.index)
    htf[f"{prefix}_ema_trend"] = np.sign(ema_fast - ema_slow)          # -1/0/1
    htf[f"{prefix}_ema_dist_pct"] = (ema_fast - ema_slow) / c * 100     # ขนาดของเทรนด์
    htf[f"{prefix}_rsi"] = rsi(c, 14)
    htf[f"{prefix}_macd_hist"] = macd_hist
    htf[f"{prefix}_atr_pct"] = atr(ohlc, 14) / c * 100
    return htf


def add_multi_timeframe_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for timeframe, prefix in [("5min", "mtf5"), ("15min", "mtf15")]:
        htf = _htf_block(df, timeframe, prefix)
        merged = pd.merge_asof(
            df.reset_index().sort_values("datetime"),
            htf.reset_index().sort_values("datetime"),
            on="datetime",
            direction="backward",   # กันหลุด look-ahead: เอาแค่แท่ง HTF ที่ปิดแล้ว
        )
        df = merged.set_index("datetime")
    return df


MTF_COLUMNS = [
    "mtf5_ema_trend", "mtf5_ema_dist_pct", "mtf5_rsi", "mtf5_macd_hist", "mtf5_atr_pct",
    "mtf15_ema_trend", "mtf15_ema_dist_pct", "mtf15_rsi", "mtf15_macd_hist", "mtf15_atr_pct",
]


# ─── 2. Microstructure / price-action ────────────────────────────────────────

def add_microstructure_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]

    is_up = (c > o).astype(int)
    is_down = (c < o).astype(int)

    # streak: จำนวนแท่งเขียว/แดงติดต่อกันล่าสุด (นับตัวเองด้วย)
    def _streak(flag: pd.Series) -> pd.Series:
        grp = (flag != flag.shift(1)).cumsum()
        return flag.groupby(grp).cumcount() + 1

    up_streak_raw = _streak(is_up)
    down_streak_raw = _streak(is_down)
    df["up_streak"] = np.where(is_up == 1, up_streak_raw, 0)
    df["down_streak"] = np.where(is_down == 1, down_streak_raw, 0)

    ret_1 = c.pct_change(1) * 100
    # momentum acceleration: การเปลี่ยนแปลงของ return 1 แท่ง เทียบแท่งก่อนหน้า
    df["momentum_accel"] = ret_1 - ret_1.shift(1)

    # realized volatility ใน rolling window สั้นๆ (std ของ ret 1 แท่ง)
    df["rvol_3"] = ret_1.rolling(3).std()
    df["rvol_5"] = ret_1.rolling(5).std()
    df["rvol_10"] = ret_1.rolling(10).std()

    # ขนาด range ทั้งแท่ง (ไม่ใช่แค่ body) และตำแหน่ง close ใน range นั้น
    df["range_pct"] = (h - l) / o * 100
    rng = (h - l).replace(0, np.nan)
    df["close_pos_in_range"] = (c - l) / rng  # 0=ปิดที่ low, 1=ปิดที่ high

    return df


MICROSTRUCTURE_COLUMNS = [
    "up_streak", "down_streak", "momentum_accel",
    "rvol_3", "rvol_5", "rvol_10",
    "range_pct", "close_pos_in_range",
]


# ─── 3. Session dummies (ละเอียดกว่า hour_sin/cos เดียว) ────────────────────

def add_session_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    hour = df.index.hour
    # เวลาโดยประมาณ (UTC) ของแต่ละ session หลักสำหรับทองคำ
    df["session_asian"] = ((hour >= 0) & (hour < 8)).astype(int)
    df["session_london"] = ((hour >= 7) & (hour < 16)).astype(int)
    df["session_ny"] = ((hour >= 12) & (hour < 21)).astype(int)
    df["session_london_ny_overlap"] = ((hour >= 12) & (hour < 16)).astype(int)
    return df


SESSION_COLUMNS = [
    "session_asian", "session_london", "session_ny", "session_london_ny_overlap",
]


# ─── 4. Mean Reversion / Reversal (สำคัญสำหรับ Option 15-30 นาที) ───────────────

def add_mean_reversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature กลุ่มกลับตัว (mean reversion) สำหรับเทรด Option ระยะสั้น
    - RSI extreme zones + slope
    - Bollinger Bands position / squeeze / width
    - Price distance from VWAP (mean reversion anchor)
    - Volume spike (unusual activity)
    - Candle rejection: upper/lower wick ratio vs body (pinbar/hammer)
    - Momentum divergence proxy: price makes HH/HL but RSI makes LH/LL
    """
    df = df.copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    # RSI levels & slope
    rsi_14 = rsi(c, 14)
    df["rsi_14"] = rsi_14
    df["rsi_14_slope"] = rsi_14.diff(3)  # slope ระยะ 3 แท่ง
    df["rsi_oversold"] = (rsi_14 < 30).astype(int)
    df["rsi_overbought"] = (rsi_14 > 70).astype(int)
    df["rsi_extreme"] = ((rsi_14 < 25) | (rsi_14 > 75)).astype(int)

    # Bollinger Bands (20, 2)
    bb_up, bb_mid, bb_low = bollinger_bands(c, 20, 2.0)
    df["bb_upper"] = bb_up
    df["bb_lower"] = bb_low
    df["bb_mid"] = bb_mid
    df["bb_width_pct"] = (bb_up - bb_low) / bb_mid * 100
    df["bb_pos"] = (c - bb_low) / (bb_up - bb_low).replace(0, np.nan)  # 0=lower, 1=upper
    df["bb_squeeze"] = (df["bb_width_pct"] < df["bb_width_pct"].rolling(20).quantile(0.2)).astype(int)

    # VWAP distance (mean reversion anchor)
    vwap_series = vwap(df)
    df["vwap"] = vwap_series
    df["dist_vwap_pct"] = (c - vwap_series) / vwap_series * 100
    df["dist_vwap_atr"] = (c - vwap_series) / atr(df, 14).replace(0, np.nan)

    # Volume spike (relative to rolling median)
    vol_median_20 = v.rolling(20).median()
    df["vol_spike"] = (v > vol_median_20 * 2.5).astype(int)
    df["vol_ratio"] = v / vol_median_20.replace(0, np.nan)

    # Candle rejection (wick / body) — pinbar / hammer detection
    body = (c - o).abs()
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l
    rng = (h - l).replace(0, np.nan)
    df["upper_wick_ratio"] = upper_wick / rng
    df["lower_wick_ratio"] = lower_wick / rng
    df["body_ratio"] = body / rng
    # Pinbar: long wick one side, small body, close near opposite end
    df["pinbar_bullish"] = (
        (lower_wick > body * 2) & (upper_wick < body * 0.5) & (c > o)
    ).astype(int)
    df["pinbar_bearish"] = (
        (upper_wick > body * 2) & (lower_wick < body * 0.5) & (c < o)
    ).astype(int)

    # Momentum divergence proxy (simplified):
    # price higher high but RSI lower high → bearish divergence
    # price lower low but RSI higher low → bullish divergence
    hh = c.rolling(5).max()
    ll = c.rolling(5).min()
    rsi_hh = rsi_14.rolling(5).max()
    rsi_ll = rsi_14.rolling(5).min()
    price_hh = (c == hh).astype(int)
    price_ll = (c == ll).astype(int)
    rsi_lh = (rsi_14.shift(1) > rsi_14).astype(int) & price_hh  # RSI falling at price HH
    rsi_hl = (rsi_14.shift(1) < rsi_14).astype(int) & price_ll  # RSI rising at price LL
    df["div_bearish"] = rsi_lh.astype(int)
    df["div_bullish"] = rsi_hl.astype(int)

    return df


MEAN_REVERSION_COLUMNS = [
    "rsi_14", "rsi_14_slope", "rsi_oversold", "rsi_overbought", "rsi_extreme",
    "bb_upper", "bb_lower", "bb_mid", "bb_width_pct", "bb_pos", "bb_squeeze",
    "vwap", "dist_vwap_pct", "dist_vwap_atr",
    "upper_wick_ratio", "lower_wick_ratio", "body_ratio",
    "pinbar_bullish", "pinbar_bearish",
    "div_bearish", "div_bullish",
]


# ─── Entry points ─────────────────────────────────────────────────────────────
#
# ผลทดลอง (three_way_split, sklearn HistGradientBoostingClassifier fallback,
# ยืนยันด้วย LightGBM จริงบนเครื่อง user อีกครั้งก่อนเชื่อ 100%):
#   - Multi-timeframe (mtf5_*, mtf15_*) คือกลุ่มที่ช่วยจริง — mtf15_ema_dist_pct,
#     mtf15_rsi, mtf15_macd_hist ติด top-3 feature importance ของ config ที่ดีที่สุด
#   - Microstructure (streak/accel/rvol/range) และ session dummies: permutation
#     importance ใกล้ 0 หรือติดลบ แทบไม่ช่วย auc_test เลย ในข้อมูล 21 วันชุดนี้
#     (อาจเป็นเพราะ hour_sin/cos เดิมจับ session ได้พอแล้ว หรือ 21 วันสั้นไป
#     ที่จะเห็น pattern price-action พวกนี้ชัด)
#
# ดังนั้น FEATURE_COLUMNS_V2 (ค่า default ที่แนะนำให้ใช้จริง) = v1 + multi-timeframe + mean_reversion
# เท่านั้น ส่วน microstructure/session ยังเก็บโค้ดไว้ให้ทดลองต่อได้ผ่าน
# FEATURE_COLUMNS_V2_FULL (เผื่อข้อมูลเยอะขึ้นแล้วอาจช่วยขึ้นก็ได้ ยังสรุปตายตัวไม่ได้
# จากข้อมูลแค่ 21 วัน)

FEATURE_COLUMNS_V2 = FEATURE_COLUMNS_V1 + MTF_COLUMNS + MEAN_REVERSION_COLUMNS
FEATURE_COLUMNS_V2_FULL = FEATURE_COLUMNS_V1 + MTF_COLUMNS + MICROSTRUCTURE_COLUMNS + SESSION_COLUMNS + MEAN_REVERSION_COLUMNS


def build_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """raw OHLCV -> features เดิมทั้งหมด + มัลติไทม์เฟรม + microstructure + session + mean_reversion
    (คำนวณทุกกลุ่มไว้เสมอ — การเลือกว่าจะ "ใช้" คอลัมน์ไหนทำที่ build_dataset_v2
    ผ่าน feature_columns เพื่อให้ทดลอง subset ต่างๆ ได้โดยไม่ต้องคำนวณซ้ำ)
    """
    df = build_features(df)              # features.py เดิม (รวม indicators พื้นฐาน)
    df = add_multi_timeframe_features(df)
    df = add_microstructure_features(df)
    df = add_session_features(df)
    df = add_mean_reversion_features(df)
    return df


def build_dataset_v2(
    df: pd.DataFrame,
    horizon: int = 5,
    deadzone_atr_mult: float = 0.0,
    feature_columns: list[str] | None = None,
):
    """เหมือน build_dataset ใน features.py แต่ใช้ feature set v2 (default = แนะนำ:
    v1 + multi-timeframe เท่านั้น). ส่ง feature_columns=FEATURE_COLUMNS_V2_FULL
    เข้ามาถ้าต้องการทดลองรวม microstructure/session ด้วย
    (แยก import make_labels จาก features.py เพื่อไม่ต้องเขียนซ้ำ)
    """
    from backend.ml_forecaster.features import make_labels

    feat_df = build_features_v2(df)
    y = make_labels(feat_df, horizon=horizon, deadzone_atr_mult=deadzone_atr_mult)

    cols = feature_columns or FEATURE_COLUMNS_V2
    X = feat_df[cols]
    valid = X.notna().all(axis=1) & y.notna()

    return X[valid], y[valid]


def get_latest_features(
    df: pd.DataFrame,
    feature_columns: list[str] | None = None,
    floor_minutes: int = 1,
) -> pd.DataFrame | None:
    """สำหรับ inference แบบ real-time: คำนวณ feature ของแท่งล่าสุด (ไม่ต้องใช้ label)

    ต่างจาก build_dataset_v2 ตรงที่:
      - ไม่ต้องมี label (ใช้กับแท่งสุดท้ายที่ยังไม่รู้ผลลัพธ์ได้)
      - ไม่มี lag จาก horizon: build_dataset_v2 ตัดแถวที่ y เป็น NaN (ช่วงท้าย)
        ทำให้ prediction เก่าอยู่ horizon แท่ง — ใช้ฟังก์ชันนี้จึงได้แท่งล่าสุดจริง
      - ตัดแท่งที่ "กำลังก่อตัว" (timestamp ตรงกับนาทีปัจจุบัน) ทิ้งเสมอ
        เพราะแท่งนั้นยังไม่ปิด ข้อมูล mid-candle อาจทำให้ feature ลำเอียง

    คืน: DataFrame 1 แถวของ feature (หรือ None ถ้าข้อมูลไม่พอ)
    """
    feat_df = build_features_v2(df)
    cols = feature_columns or FEATURE_COLUMNS_V2
    # กัน feature mismatch: โมเดล hybrid (มี st_* จาก setup_scorer) ส่ง feature_columns
    # ครบชุด แต่ cột setup ถูก merge เพิ่มทีหลังใน notifier — กรองเฉพาะ cộtราคาที่มี
    cols = [c for c in cols if c in feat_df.columns] or FEATURE_COLUMNS_V2

    f = feat_df[cols].dropna()
    if f.empty:
        return None

    # ตัดแท่งกำลังก่อตัว (bar ที่ยังไม่ปิด ตรงกับช่วงเวลาปัจจุบัน) ทิ้ง — ข้อมูล
    # mid-candle ของแท่งนั้นอาจลำเอียง และยังไม่มีราคาปิดจริง
    now = pd.Timestamp.now(tz="UTC")
    if len(f) > 1 and f.index[-1] == now.floor(f"{floor_minutes}min"):
        f = f.iloc[:-1]

    return f.iloc[[-1]] if len(f) else None
