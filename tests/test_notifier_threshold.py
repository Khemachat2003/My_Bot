"""Characterization tests — backend/notifier.py เฉพาะ _conf_threshold

ล็อกลำดับความสำคัญของ threshold: env ML_CONF_THRESHOLD > chosen_conf ของโมเดล > 0.55
(หมายเหตุ: import backend.notifier จะโหลดโมเดล joblib จริงที่มีอยู่ — ไม่มีเน็ต/ไม่มี DB)
"""
import pytest

from backend.notifier import MODELS, _conf_threshold


def test_env_overrides_everything(monkeypatch):
    monkeypatch.setenv("ML_CONF_THRESHOLD", "0.72")
    assert _conf_threshold("M1") == 0.72
    assert _conf_threshold("M5") == 0.72


def test_env_whitespace_still_counts(monkeypatch):
    monkeypatch.setenv("ML_CONF_THRESHOLD", "  0.65  ")
    assert _conf_threshold("M5") == 0.65


def test_env_invalid_value_falls_back(monkeypatch):
    monkeypatch.setenv("ML_CONF_THRESHOLD", "not-a-number")
    expected = MODELS.get("M5", {}).get("chosen_conf") or 0.55
    assert _conf_threshold("M5") == expected


def test_env_unset_falls_back_to_model_or_default(monkeypatch):
    monkeypatch.delenv("ML_CONF_THRESHOLD", raising=False)
    expected = MODELS.get("M5", {}).get("chosen_conf") or 0.55
    assert _conf_threshold("M5") == expected
    expected_m1 = MODELS.get("M1", {}).get("chosen_conf") or 0.55
    assert _conf_threshold("M1") == expected_m1


def test_threshold_is_float_in_valid_range(monkeypatch):
    monkeypatch.delenv("ML_CONF_THRESHOLD", raising=False)
    val = _conf_threshold("M5")
    assert isinstance(val, float)
    assert 0.0 < val < 1.0