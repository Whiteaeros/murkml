"""Tests for Round 1A data pipeline fixes in assemble_dataset.py.

Covers:
- Fix 1:  Timezone conversion (local → UTC)
- Fix 6:  Drop rows with missing time/timezone
- Fix 8:  Value-range QC (negative and extreme values)
- Fix 11: Non-detect handling (DL/2 substitution, SSC=0 kept)
- Fix 18: Deduplication of discrete samples

Uses synthetic data only — no API calls or file I/O.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Make assemble_dataset importable (it lives in scripts/, not an installed package)
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from assemble_dataset import load_discrete, USGS_TZ_OFFSETS
from murkml.data.qc import filter_continuous


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parquet_for_discrete(rows: list[dict], tmp_path: Path, site_id: str = "01-234") -> Path:
    """Write a fake discrete parquet and return the directory it lives in."""
    df = pd.DataFrame(rows)
    site_stem = site_id.replace("-", "_")
    out = tmp_path / "discrete" / f"{site_stem}_ssc.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return tmp_path


def _call_load_discrete(tmp_path: Path, rows: list[dict], site_id: str = "01-234"):
    """Helper: write parquet, patch DATA_DIR, call load_discrete."""
    data_dir = _parquet_for_discrete(rows, tmp_path, site_id)
    with patch("assemble_dataset.DATA_DIR", data_dir):
        return load_discrete(site_id)


# ===================================================================
# Fix 1 — Timezone conversion (local timestamps → UTC)
# ===================================================================

class TestTimezoneConversion:
    """Fix 1: Convert local timestamps to UTC using USGS_TZ_OFFSETS."""

    def test_cst_to_utc(self, tmp_path):
        """CST (UTC-6): 10:00 AM CST → 16:00 UTC."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "CST",
            "Result_Measure": "50",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["datetime"].hour == 16

    def test_est_to_utc(self, tmp_path):
        """EST (UTC-5): 10:00 AM EST → 15:00 UTC."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "50",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["datetime"].hour == 15

    def test_pst_to_utc(self, tmp_path):
        """PST (UTC-8): 10:00 AM PST → 18:00 UTC."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "PST",
            "Result_Measure": "50",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["datetime"].hour == 18

    def test_utc_passthrough(self, tmp_path):
        """UTC offset is 0, so time should be unchanged."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "UTC",
            "Result_Measure": "50",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["datetime"].hour == 10

    def test_missing_timezone_dropped(self, tmp_path):
        """Rows with NaN timezone are dropped (Fix 1/6)."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": None,
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "11:00:00",
                "Activity_StartTimeZone": "CST",
                "Result_Measure": "60",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        # Only the CST row survives
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == 60.0

    def test_missing_starttime_dropped(self, tmp_path):
        """Rows with missing Activity_StartTime are dropped (Fix 6)."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": None,
                "Activity_StartTimeZone": "CST",
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "11:00:00",
                "Activity_StartTimeZone": "CST",
                "Result_Measure": "60",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == 60.0

    def test_empty_starttime_dropped(self, tmp_path):
        """Empty-string Activity_StartTime is treated as missing."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "",
                "Activity_StartTimeZone": "CST",
                "Result_Measure": "50",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 0

    def test_unrecognized_timezone_dropped(self, tmp_path, caplog):
        """Unrecognized timezone codes are dropped with a warning log."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "XYZ",
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "11:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "60",
            },
        ]
        with caplog.at_level(logging.WARNING):
            result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == 60.0
        # Check that a warning was logged about the unrecognized timezone
        assert any("unrecognized timezone" in msg.lower() for msg in caplog.messages)

    def test_tz_offsets_dict_completeness(self):
        """Verify USGS_TZ_OFFSETS covers the standard US timezones."""
        expected_keys = {"EST", "EDT", "CST", "CDT", "MST", "MDT", "PST", "PDT", "UTC"}
        assert expected_keys.issubset(set(USGS_TZ_OFFSETS.keys()))


# ===================================================================
# Fix 11 — Non-detect handling (DL/2 substitution)
# ===================================================================

class TestNonDetectHandling:
    """Fix 11: Non-detects get DL/2 substitution; SSC=0 is kept."""

    def test_nondetect_dl2_substitution(self, tmp_path):
        """Non-detect with DL=4 → ssc_value = 2.0 (DL/2)."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "4",
            "Result_ResultDetectionCondition": "Not Detected",
            "DetectionQuantitationLimitMeasure_MeasureValue": "4",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == pytest.approx(2.0)
        assert bool(result.iloc[0]["is_nondetect"]) is True

    def test_nondetect_fallback_to_result_measure(self, tmp_path):
        """When DL column is missing, fall back to Result_Measure as the DL."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "6",
            "Result_ResultDetectionCondition": "Not Detected",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == pytest.approx(3.0)  # 6 / 2
        assert bool(result.iloc[0]["is_nondetect"]) is True

    def test_ssc_zero_kept(self, tmp_path):
        """SSC=0 is a valid measurement and should not be dropped."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "0",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert result.iloc[0]["ssc_value"] == 0.0

    def test_detected_sample_flag_false(self, tmp_path):
        """Normal detected samples get is_nondetect = False."""
        rows = [{
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "100",
        }]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1
        assert bool(result.iloc[0]["is_nondetect"]) is False

    def test_nondetect_flag_mixed(self, tmp_path):
        """Mix of detected and non-detected: flags set correctly."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "100",
            },
            {
                "Activity_StartDate": "2024-06-16",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "2",
                "Result_ResultDetectionCondition": "Not Detected",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 2
        detected = result[result["ssc_value"] == 100.0]
        nondetect = result[result["ssc_value"] == 1.0]  # 2 / 2 = 1.0
        assert bool(detected.iloc[0]["is_nondetect"]) is False
        assert bool(nondetect.iloc[0]["is_nondetect"]) is True


# ===================================================================
# Fix 18 — Deduplication
# ===================================================================

class TestDeduplication:
    """Fix 18: Duplicate (datetime, ssc_value) rows are removed."""

    def test_exact_duplicate_removed(self, tmp_path):
        """Two identical rows → only one kept."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "50",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 1

    def test_different_values_same_time_kept(self, tmp_path):
        """Same time but different SSC values — both kept."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "75",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 2

    def test_same_value_different_time_kept(self, tmp_path):
        """Same SSC value but different times — both kept."""
        rows = [
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "10:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "50",
            },
            {
                "Activity_StartDate": "2024-06-15",
                "Activity_StartTime": "11:00:00",
                "Activity_StartTimeZone": "EST",
                "Result_Measure": "50",
            },
        ]
        result = _call_load_discrete(tmp_path, rows)
        assert len(result) == 2

    def test_triple_duplicate_reduced_to_one(self, tmp_path):
        """Three identical rows → one kept."""
        row = {
            "Activity_StartDate": "2024-06-15",
            "Activity_StartTime": "10:00:00",
            "Activity_StartTimeZone": "EST",
            "Result_Measure": "50",
        }
        result = _call_load_discrete(tmp_path, [row, row, row])
        assert len(result) == 1


# ===================================================================
# Fix 8 — Value-range QC (via filter_continuous)
# ===================================================================

class TestValueRangeQC:
    """Fix 8: Negative and extreme values excluded by filter_continuous."""

    @staticmethod
    def _make_continuous(rows: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        if "approval_status" not in df.columns:
            df["approval_status"] = "Approved"
        if "qualifier" not in df.columns:
            df["qualifier"] = ""
        return df

    def test_negative_value_excluded(self):
        """Values below -0.01 are excluded by range QC."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0},
            {"datetime": "2024-06-01T12:15", "value": -5.0},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert filtered.iloc[0]["value"] == 10.0
        assert stats["n_range_excluded"] == 1

    def test_extreme_value_excluded(self):
        """Values above 100,000 are excluded by range QC."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0},
            {"datetime": "2024-06-01T12:15", "value": 200_000.0},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert filtered.iloc[0]["value"] == 10.0
        assert stats["n_range_excluded"] == 1

    def test_boundary_value_kept(self):
        """Value of exactly 100,000 is within bounds and kept."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 100_000.0},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert stats["n_range_excluded"] == 0

    def test_zero_value_kept(self):
        """Value of 0.0 is within bounds and kept."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 0.0},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1

    def test_slightly_negative_kept(self):
        """Value of -0.005 is within the -0.01 tolerance and kept."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": -0.005},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert stats["n_range_excluded"] == 0

    def test_mixed_good_and_bad_values(self):
        """Only out-of-range values excluded; valid data preserved."""
        df = self._make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 5.0},
            {"datetime": "2024-06-01T12:15", "value": -100.0},
            {"datetime": "2024-06-01T12:30", "value": 50.0},
            {"datetime": "2024-06-01T12:45", "value": 999_999.0},
            {"datetime": "2024-06-01T13:00", "value": 25.0},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 3
        assert set(filtered["value"]) == {5.0, 50.0, 25.0}
        assert stats["n_range_excluded"] == 2
