"""
setup_features.py — แปลง setup_scorer output → feature vector สำหรับ ML (Hybrid)
=================================================================================
ให้ ML เรียนรู้ "บริบท" เดียวกับที่ Rule-Based ใช้ (10 checklist + score/direction/tier)
ทั้งตอน train (auto_retrain) และตอน predict (notifier) ใช้ชุดคอลัมน์เดียวกัน
เพื่อให้ model ไม่เห็น cộtชุดต่างกันตอนเทรน vs ตอนรันจริง (กัน feature mismatch)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.setup_scorer import SetupResult

# V8: 10 conditions ใน details ของ score_setup → flatten เป็นคอลัมน์ตัวเลข
SETUP_DETAIL_KEYS = ["c1_fractal_sr", "c2_bb_break", "c3_rsi_ob_os", "c4_rsi_div",
                     "c5_adx", "c6_pa", "c7_fractal_trend", "c8_grip",
                     "c9_bb_width", "c10_mtf"]
_TIER_ENC = {"NONE": 0, "WATCH": 1, "FIRE": 2}
_DIR_ENC = {"CALL": 1, "PUT": -1}

SETUP_FEATURE_COLUMNS = sorted({
    *(f"st_{k}_ok" for k in SETUP_DETAIL_KEYS),
    *(f"st_{k}_frac" for k in SETUP_DETAIL_KEYS),
    "st_score", "st_score_ratio", "st_direction", "st_tier",
    "st_entry_trigger",
})


def flatten_setup_dict(row: dict) -> dict:
    """แปลง dict ที่อ่านจาก setup_scores (DB) → dict feature ตัวเลข"""
    details = row.get("details") or {}
    return _flatten(details,
                    score=row.get("score"),
                    max_score=row.get("max_score"),
                    direction=row.get("direction"),
                    tier=row.get("tier"),
                    entry_trigger=row.get("entry_trigger"))


def flatten_setup_result(result: "SetupResult") -> dict:
    """แปลง SetupResult (จาก score_setup ตอนรันสด) → dict feature ตัวเลข
    ใช้ใน notifier ตอน predict ให้ features ตรงกับตอนเทรนเป๊ะ"""
    return _flatten(result.details,
                    score=result.score,
                    max_score=result.max_score,
                    direction=result.direction,
                    tier=result.tier,
                    entry_trigger=result.entry_trigger)


def _flatten(details: dict, score, max_score, direction, tier,
             entry_trigger) -> dict:
    out = {}
    for k in SETUP_DETAIL_KEYS:
        d = details.get(k)
        if isinstance(d, dict):
            out[f"st_{k}_ok"] = 1.0 if d.get("ok") else 0.0
            out[f"st_{k}_frac"] = float(d.get("frac", 0.0))
        else:
            out[f"st_{k}_ok"] = 0.0
            out[f"st_{k}_frac"] = 0.0
    out["st_score"] = float(score or 0.0)
    out["st_score_ratio"] = float(score or 0.0) / max(float(max_score or 15.0), 1.0)
    out["st_direction"] = float(_DIR_ENC.get(direction, 0.0))
    out["st_tier"] = float(_TIER_ENC.get(tier, 0.0))
    out["st_entry_trigger"] = 1.0 if entry_trigger else 0.0
    return out


def setup_features_from_result(result: "SetupResult") -> dict:
    """alias — คืน feature dict (เก็บไว้ใน ml_signals.features_json ตอนยิง)"""
    return flatten_setup_result(result)
