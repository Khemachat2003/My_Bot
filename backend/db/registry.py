"""db.registry — model registry (version โมเดลที่เคยเทรน) — ย้ายจาก db.py แบบ move-only"""

from __future__ import annotations

from backend.db.connection import get_conn

# ─── MODEL REGISTRY ──────────────────────────────────────────────────────────


def register_model(
    model_key: str,
    version: str,
    trained_at: str,
    horizon: int,
    n_rows: int | None,
    auc_val: float | None,
    auc_test: float | None,
    chosen_conf: float | None,
    feature_set: str | None = None,
    note: str | None = None,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO model_registry
           (model_key, version, trained_at, horizon, n_rows, auc_val, auc_test,
            chosen_conf, feature_set, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(model_key, version) DO UPDATE SET
             trained_at=excluded.trained_at, n_rows=excluded.n_rows,
             auc_val=excluded.auc_val, auc_test=excluded.auc_test,
             chosen_conf=excluded.chosen_conf, feature_set=excluded.feature_set,
             note=excluded.note""",
        (
            model_key,
            version,
            trained_at,
            horizon,
            n_rows,
            auc_val,
            auc_test,
            chosen_conf,
            feature_set,
            note,
        ),
    )
    conn.commit()
    conn.close()


def fetch_model_registry(limit: int = 20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM model_registry ORDER BY trained_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
