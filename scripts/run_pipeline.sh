#!/bin/bash
# Run the full murkml data pipeline.
# Usage: bash scripts/run_pipeline.sh
#
# Prerequisites:
# - .env file with API_USGS_PAT token
# - pip install -e ".[all,dev]"

set -e

PYTHON=".venv/Scripts/python.exe"

echo "=== Step 1: Download data ==="
$PYTHON scripts/download_data.py --n-sites 20 --years 15 --delay 2

echo ""
echo "=== Step 2: Retry any failed discrete downloads ==="
$PYTHON scripts/retry_discrete.py

echo ""
echo "=== Step 3: Assemble ML-ready dataset ==="
$PYTHON scripts/assemble_dataset.py

echo ""
echo "=== Step 4: Data exploration ==="
$PYTHON notebooks/01_data_exploration.py

echo ""
echo "=== Step 5: Train baseline models ==="
$PYTHON scripts/train_baseline.py

echo ""
echo "=== Pipeline complete! ==="
echo "Results at: data/results/baseline_results.parquet"
echo "Figures at: notebooks/figures/"
