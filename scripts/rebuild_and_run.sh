#!/usr/bin/env bash
# Re-build Qlib data and run monthly LightGBM benchmark, with the full survivorship-bias-free universe.
set -e
cd /d/PM/jr

# 1. Post-process: ensure vwap exists in all CSVs (the new 274 don't have it yet)
echo "=== adding vwap to new CSVs ==="
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/postprocess.py

# 2. Re-dump bin with the full universe
echo "=== rebuilding qlib bin (full universe) ==="
rm -rf qlib_data/cn_data
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe projects/qlib/scripts/dump_bin.py dump_all \
  --data_path qlib_data/csv \
  --qlib_dir qlib_data/cn_data \
  --freq day --date_field_name date --symbol_field_name symbol \
  --include_fields open,close,high,low,volume,amount,turnover,factor,vwap

# 3. Generate csi300_history.txt for Qlib (instrument file with time-varying membership)
echo "=== installing csi300_history.txt as the csi300 instrument file ==="
cp qlib_data/csi300_history.txt qlib_data/cn_data/instruments/csi300.txt

# 4. Re-run monthly LightGBM
echo "=== running monthly LightGBM (Alpha158, survivorship-fixed) ==="
PYTHONIOENCODING=utf-8 .venv/Scripts/qrun.exe configs/lgb_alpha158_monthly.yaml
