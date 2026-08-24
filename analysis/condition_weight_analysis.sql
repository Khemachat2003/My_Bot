-- condition_weight_analysis.sql
-- วิเคราะห์น้ำหนักของ checklist แต่ละตัว จาก setup_signals ที่มีผล WIN/LOSE แล้ว
-- รันบน VPS:  sqlite3 data/bot.db < analysis/condition_weight_analysis.sql
--
-- เป้าหมาย: 找出ว่า checklist ตัวไหนมี "สัญญาณน้ำหนัก" จริง (ชนะเมื่อมี vs ชนะเมื่อไม่มี)
-- ถ้า c1_fractal_sr มีอยู่ใน 80% ของ WIN → weight สูง
-- ถ้า c2_bb_break มีอยู่ในทั้ง WIN และ LOSE เท่ากัน → weight ต่ำ (noise)

-- ═══ 1. Win-Rate ของแต่ละ Checklist (แยกตาม direction) ═══
SELECT '=== CONDITION WINRATE ===' as section;
SELECT
  direction,
  CASE
    WHEN json_extract(conditions_log_json, '$.c1_fractal_sr.pass') = 1 THEN 'c1_fractal_sr'
    WHEN json_extract(conditions_log_json, '$.c2_bb_break.pass') = 1 THEN 'c2_bb_break'
    WHEN json_extract(conditions_log_json, '$.c3_rsi_ob_os.pass') = 1 THEN 'c3_rsi_ob_os'
    WHEN json_extract(conditions_log_json, '$.c4_rsi_div.pass') = 1 THEN 'c4_rsi_div'
    WHEN json_extract(conditions_log_json, '$.c5_adx.pass') = 1 THEN 'c5_adx'
    WHEN json_extract(conditions_log_json, '$.c6_pa.pass') = 1 THEN 'c6_pa'
    WHEN json_extract(conditions_log_json, '$.c7_fractal_trend.pass') = 1 THEN 'c7_fractal_trend'
    WHEN json_extract(conditions_log_json, '$.c8_grip.pass') = 1 THEN 'c8_grip'
    WHEN json_extract(conditions_log_json, '$.c9_bb_width.pass') = 1 THEN 'c9_bb_width'
    WHEN json_extract(conditions_log_json, '$.c10_mtf.pass') = 1 THEN 'c10_mtf'
  END as condition,
  COUNT(*) as total,
  SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
  ROUND(100.0 * SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) / COUNT(*), 1) as winrate
FROM setup_signals
WHERE phantom = 0
  AND result IN ('WIN', 'LOSE')
  AND conditions_log_json IS NOT NULL
GROUP BY direction, condition
ORDER BY direction, winrate DESC;

-- ═══ 2. Pairwise: Win-Rate เมื่อมี condition X vs ไม่มี ═══
SELECT '=== CONDITION LIFT (WR with condition / WR without) ===' as section;
-- ทำทีละ condition ด้วย UNION ALL
SELECT direction, 'c1_fractal_sr' as cond,
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c1_fractal_sr.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c1_fractal_sr.pass')=1 THEN 1 ELSE 0 END),0), 1) as wr_with,
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c1_fractal_sr.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c1_fractal_sr.pass')!=1 THEN 1 ELSE 0 END),0), 1) as wr_without
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c2_bb_break',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c2_bb_break.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c2_bb_break.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c2_bb_break.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c2_bb_break.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c3_rsi_ob_os',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c3_rsi_ob_os.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c3_rsi_ob_os.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c3_rsi_ob_os.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c3_rsi_ob_os.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c4_rsi_div',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c4_rsi_div.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c4_rsi_div.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c4_rsi_div.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c4_rsi_div.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c5_adx',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c5_adx.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c5_adx.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c5_adx.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c5_adx.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c6_pa',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c6_pa.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c6_pa.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c6_pa.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c6_pa.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c7_fractal_trend',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c7_fractal_trend.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c7_fractal_trend.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c7_fractal_trend.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c7_fractal_trend.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c8_grip',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c8_grip.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c8_grip.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c8_grip.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c8_grip.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c9_bb_width',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c9_bb_width.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c9_bb_width.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c9_bb_width.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c9_bb_width.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
UNION ALL
SELECT direction, 'c10_mtf',
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c10_mtf.pass')=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c10_mtf.pass')=1 THEN 1 ELSE 0 END),0), 1),
  ROUND(100.0 * SUM(CASE WHEN result='WIN' AND json_extract(conditions_log_json,'$.c10_mtf.pass')!=1 THEN 1 ELSE 0 END)
    / NULLIF(SUM(CASE WHEN json_extract(conditions_log_json,'$.c10_mtf.pass')!=1 THEN 1 ELSE 0 END),0), 1)
FROM setup_signals WHERE phantom=0 AND result IN ('WIN','LOSE') AND conditions_log_json IS NOT NULL
GROUP BY direction
ORDER BY direction, wr_with DESC;

-- ═══ 3. Count signals with conditions_log (data readiness) ═══
SELECT '=== DATA READINESS ===' as section;
SELECT
  COUNT(*) as total_signals,
  SUM(CASE WHEN conditions_log_json IS NOT NULL THEN 1 ELSE 0 END) as has_conditions_log,
  SUM(CASE WHEN conditions_log_json IS NOT NULL AND result IN ('WIN','LOSE') THEN 1 ELSE 0 END) as resolved_with_log
FROM setup_signals
WHERE phantom = 0;
