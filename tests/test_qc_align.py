"""Tests for QC filtering, temporal alignment, and feature engineering.

Uses synthetic data only — no API calls.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from murkml.data.qc import filter_continuous, EXCLUDE_QUALIFIERS, KEEP_QUALIFIERS
from murkml.data.align import align_samples, PRIMARY_WINDOW, FEATURE_WINDOW
from murkml.data.features import (
    add_seasonality,
    add_cross_sensor_features,
    engineer_features,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_continuous(
    rows: list[dict],
    time_col: str = "datetime",
) -> pd.DataFrame:
    """Build a continuous-sensor DataFrame from a list of row dicts.

    Each dict should contain at minimum 'datetime' and 'value'.
    Adds default columns (approval_status, qualifier) when absent.
    """
    df = pd.DataFrame(rows)
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    if "approval_status" not in df.columns:
        df["approval_status"] = "Approved"
    if "qualifier" not in df.columns:
        df["qualifier"] = ""
    return df


def _make_discrete(
    rows: list[dict],
    time_col: str = "datetime",
) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    return df


# ===================================================================
# QC filtering tests  (qc.py)
# ===================================================================

class TestQCApprovalFilter:
    """Approval-status filtering."""

    def test_approved_data_kept(self):
        df = _make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0, "approval_status": "Approved"},
            {"datetime": "2024-06-01T12:15", "value": 11.0, "approval_status": "Approved"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 2
        assert stats["n_not_approved"] == 0

    def test_provisional_excluded(self):
        df = _make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0, "approval_status": "Approved"},
            {"datetime": "2024-06-01T12:15", "value": 11.0, "approval_status": "Provisional"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert filtered.iloc[0]["value"] == 10.0
        assert stats["n_not_approved"] == 1


class TestQCQualifierFilter:
    """Qualifier-code filtering."""

    def test_ice_excluded(self):
        df = _make_continuous([
            {"datetime": "2024-01-15T08:00", "value": 5.0, "qualifier": "Ice"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 0
        assert stats["n_bad_qualifier"] == 1

    def test_eqp_excluded(self):
        df = _make_continuous([
            {"datetime": "2024-03-01T10:00", "value": 99.0, "qualifier": "Eqp"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 0
        assert stats["n_bad_qualifier"] == 1

    def test_fld_kept(self):
        df = _make_continuous([
            {"datetime": "2024-04-10T14:00", "value": 250.0, "qualifier": "Fld"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1
        assert filtered.iloc[0]["value"] == 250.0

    def test_none_qualifier_kept(self):
        df = _make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0, "qualifier": None},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1

    def test_empty_string_qualifier_kept(self):
        df = _make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10.0, "qualifier": ""},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 1

    def test_comma_separated_qualifiers_with_bad(self):
        """A record with 'Fld,Ice' should be excluded because Ice is bad."""
        df = _make_continuous([
            {"datetime": "2024-04-10T14:00", "value": 200.0, "qualifier": "Fld,Ice"},
        ])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 0


class TestQCStats:
    """Stats dict correctness."""

    def test_stats_counts(self):
        df = _make_continuous([
            {"datetime": "2024-06-01T12:00", "value": 10, "approval_status": "Approved", "qualifier": ""},
            {"datetime": "2024-06-01T12:15", "value": 11, "approval_status": "Provisional", "qualifier": ""},
            {"datetime": "2024-06-01T12:30", "value": 12, "approval_status": "Approved", "qualifier": "Ice"},
            {"datetime": "2024-06-01T12:45", "value": 13, "approval_status": "Approved", "qualifier": "Fld"},
        ])
        filtered, stats = filter_continuous(df)
        assert stats["n_original"] == 4
        assert stats["n_not_approved"] == 1  # Provisional
        assert stats["n_bad_qualifier"] == 1  # Ice (only among Approved rows)
        assert stats["n_after_filter"] == 2   # Approved clean + Fld
        assert stats["pct_retained"] == 50.0

    def test_empty_input(self):
        df = pd.DataFrame(columns=["datetime", "value", "approval_status", "qualifier"])
        filtered, stats = filter_continuous(df)
        assert len(filtered) == 0
        assert stats["n_original"] == 0


class TestQCRealisticMixed:
    """Realistic scenario mixing many conditions."""

    def test_mixed_data(self):
        rows = [
            # Good data
            {"datetime": "2024-06-01T08:00", "value": 10.0, "approval_status": "Approved", "qualifier": ""},
            {"datetime": "2024-06-01T08:15", "value": 10.5, "approval_status": "Approved", "qualifier": None},
            # Flood — should survive
            {"datetime": "2024-06-01T08:30", "value": 250.0, "approval_status": "Approved", "qualifier": "Fld"},
            # Ice — excluded
            {"datetime": "2024-01-15T08:00", "value": 0.5, "approval_status": "Approved", "qualifier": "Ice"},
            # Equipment malfunction — excluded
            {"datetime": "2024-06-01T09:00", "value": -999.0, "approval_status": "Approved", "qualifier": "Eqp"},
            # Provisional — excluded at approval step
            {"datetime": "2024-06-01T09:15", "value": 12.0, "approval_status": "Provisional", "qualifier": ""},
            # Bkw — excluded
            {"datetime": "2024-06-01T09:30", "value": 8.0, "approval_status": "Approved", "qualifier": "Bkw"},
            # Mnt — excluded
            {"datetime": "2024-06-01T09:45", "value": 9.0, "approval_status": "Approved", "qualifier": "Mnt"},
        ]
        df = _make_continuous(rows)
        filtered, stats = filter_continuous(df)

        # Expect: 2 clean + 1 Fld = 3 records
        assert len(filtered) == 3
        assert set(filtered["value"]) == {10.0, 10.5, 250.0}


# ===================================================================
# Temporal alignment tests  (align.py)
# ===================================================================

def _sensor_timeseries(start: str, periods: int = 9, freq: str = "15min", values=None):
    """Build a 15-min continuous sensor DataFrame over a span."""
    times = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    if values is None:
        values = np.arange(1.0, periods + 1)
    return pd.DataFrame({"datetime": times, "value": values})


class TestAlignBasic:
    """Primary match behaviour."""

    def test_exact_match(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=5)
        disc = _make_discrete([
            {"datetime": "2024-06-01T12:30", "value": 100.0},
        ])
        result = align_samples(cont, disc)
        assert len(result) == 1
        assert result.iloc[0]["sensor_instant"] == 3.0  # 3rd reading (12:30)
        assert result.iloc[0]["match_gap_seconds"] == 0.0

    def test_small_offset_within_window(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=5)
        # Sample at 12:37 — nearest sensor reading is 12:30 (7 min gap)
        disc = _make_discrete([
            {"datetime": "2024-06-01T12:37", "value": 100.0},
        ])
        result = align_samples(cont, disc)
        assert len(result) == 1
        assert result.iloc[0]["sensor_instant"] == 3.0  # 12:30 reading
        assert result.iloc[0]["match_gap_seconds"] == pytest.approx(7 * 60, abs=1)

    def test_outside_window_dropped(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=3)
        # Sample at 14:00 — well past sensor coverage ending at 12:30
        disc = _make_discrete([
            {"datetime": "2024-06-01T14:00", "value": 100.0},
        ])
        result = align_samples(cont, disc)
        assert len(result) == 0


class TestAlignWindowFeatures:
    """Window-derived statistics (±1 hr feature window)."""

    def test_window_features_known_values(self):
        # 9 readings at 15-min intervals: 12:00 to 14:00
        # Values: constant 10.0 so stats are trivially checkable
        times = pd.date_range("2024-06-01T12:00", periods=9, freq="15min", tz="UTC")
        values = [10.0] * 9
        cont = pd.DataFrame({"datetime": times, "value": values})

        # Sample at 13:00 — the middle. ±1 hr window is 12:00–14:00 = all 9 readings
        disc = _make_discrete([
            {"datetime": "2024-06-01T13:00", "value": 50.0},
        ])
        result = align_samples(cont, disc)
        row = result.iloc[0]

        assert row["window_mean"] == pytest.approx(10.0)
        assert row["window_min"] == pytest.approx(10.0)
        assert row["window_max"] == pytest.approx(10.0)
        assert row["window_std"] == pytest.approx(0.0)
        assert row["window_slope"] == pytest.approx(0.0, abs=1e-10)
        assert row["window_count"] == 9

    def test_window_slope_linear(self):
        # Linearly increasing: 1,2,3,...,9 at 15-min spacing
        times = pd.date_range("2024-06-01T12:00", periods=9, freq="15min", tz="UTC")
        cont = pd.DataFrame({"datetime": times, "value": np.arange(1.0, 10.0)})

        disc = _make_discrete([
            {"datetime": "2024-06-01T13:00", "value": 50.0},
        ])
        result = align_samples(cont, disc)
        row = result.iloc[0]

        # Slope should be 1 unit per 900 seconds = 1/900 ≈ 0.001111
        assert row["window_slope"] == pytest.approx(1.0 / 900.0, rel=0.01)

    def test_window_range(self):
        times = pd.date_range("2024-06-01T12:00", periods=9, freq="15min", tz="UTC")
        cont = pd.DataFrame({"datetime": times, "value": np.arange(1.0, 10.0)})

        disc = _make_discrete([
            {"datetime": "2024-06-01T13:00", "value": 50.0},
        ])
        result = align_samples(cont, disc)
        assert result.iloc[0]["window_range"] == pytest.approx(8.0)


class TestAlignMultipleAndEdgeCases:
    """Multiple samples and empty inputs."""

    def test_multiple_samples(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=9)
        disc = _make_discrete([
            {"datetime": "2024-06-01T12:00", "value": 100.0},
            {"datetime": "2024-06-01T12:30", "value": 200.0},
            {"datetime": "2024-06-01T13:00", "value": 300.0},
        ])
        result = align_samples(cont, disc)
        assert len(result) == 3
        assert list(result["lab_value"]) == [100.0, 200.0, 300.0]

    def test_empty_continuous(self):
        cont = pd.DataFrame(columns=["datetime", "value"])
        disc = _make_discrete([{"datetime": "2024-06-01T12:00", "value": 100.0}])
        result = align_samples(cont, disc)
        assert len(result) == 0

    def test_empty_discrete(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=5)
        disc = pd.DataFrame(columns=["datetime", "value"])
        result = align_samples(cont, disc)
        assert len(result) == 0

    def test_match_gap_seconds_accuracy(self):
        cont = _sensor_timeseries("2024-06-01T12:00", periods=5)
        # 10 minutes after 12:15 → nearest is 12:15, gap = 10 min = 600 s
        disc = _make_discrete([
            {"datetime": "2024-06-01T12:25", "value": 100.0},
        ])
        result = align_samples(cont, disc)
        assert len(result) == 1
        # Nearest is 12:30 (5 min gap) not 12:15 (10 min gap)
        assert result.iloc[0]["match_gap_seconds"] == pytest.approx(5 * 60, abs=1)
        assert result.iloc[0]["sensor_instant"] == 3.0  # value at 12:30


# ===================================================================
# Feature engineering tests  (features.py)
# ===================================================================

class TestSeasonality:
    """Sin/cos day-of-year encoding."""

    def test_jan_vs_jul(self):
        df = pd.DataFrame({
            "sample_time": pd.to_datetime(["2024-01-15", "2024-07-15"]),
        })
        result = add_seasonality(df)
        jan_sin = result.iloc[0]["doy_sin"]
        jul_sin = result.iloc[1]["doy_sin"]
        # January DOY ~15, July DOY ~197 — these should be very different
        assert jan_sin != pytest.approx(jul_sin, abs=0.1)

    def test_sin_cos_range(self):
        """All values should be in [-1, 1]."""
        times = pd.date_range("2024-01-01", periods=365, freq="D")
        df = pd.DataFrame({"sample_time": times})
        result = add_seasonality(df)
        assert result["doy_sin"].between(-1, 1).all()
        assert result["doy_cos"].between(-1, 1).all()

    def test_december_wraps_near_january(self):
        """Dec 31 and Jan 1 should have similar encodings (circular feature)."""
        df = pd.DataFrame({
            "sample_time": pd.to_datetime(["2024-01-01", "2024-12-31"]),
        })
        result = add_seasonality(df)
        # DOY 1 and DOY 366 should produce nearly the same sin/cos
        assert result.iloc[0]["doy_sin"] == pytest.approx(result.iloc[1]["doy_sin"], abs=0.05)
        assert result.iloc[0]["doy_cos"] == pytest.approx(result.iloc[1]["doy_cos"], abs=0.05)


class TestCrossSensorFeatures:
    """Cross-sensor interactions."""

    def test_turb_Q_ratio(self):
        df = pd.DataFrame({
            "turbidity_instant": [100.0, 200.0],
            "discharge_instant": [50.0, 100.0],
        })
        result = add_cross_sensor_features(df)
        assert "turb_Q_ratio" in result.columns
        assert result.iloc[0]["turb_Q_ratio"] == pytest.approx(2.0)
        assert result.iloc[1]["turb_Q_ratio"] == pytest.approx(2.0)

    def test_turb_Q_ratio_zero_discharge(self):
        """Zero discharge should produce NaN, not an error."""
        df = pd.DataFrame({
            "turbidity_instant": [100.0],
            "discharge_instant": [0.0],
        })
        result = add_cross_sensor_features(df)
        assert np.isnan(result.iloc[0]["turb_Q_ratio"])

    def test_do_saturation_departure(self):
        # DO_sat = 14.6 - 0.4 * temp
        # temp=10 → DO_sat=10.6, DO=9.0 → departure = -1.6
        df = pd.DataFrame({
            "do_instant": [9.0],
            "temp_instant": [10.0],
        })
        result = add_cross_sensor_features(df)
        assert "DO_sat_departure" in result.columns
        assert result.iloc[0]["DO_sat_departure"] == pytest.approx(-1.6)

    def test_missing_columns_no_error(self):
        """If sensor columns are absent, function should not crash."""
        df = pd.DataFrame({"other_col": [1, 2, 3]})
        result = add_cross_sensor_features(df)
        assert "turb_Q_ratio" not in result.columns
        assert "DO_sat_departure" not in result.columns
