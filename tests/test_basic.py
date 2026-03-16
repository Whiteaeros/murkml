"""Basic tests to verify murkml imports and core functions work."""

import numpy as np


def test_import():
    import murkml
    assert murkml.__version__ is not None


def test_random_seed():
    from murkml import RANDOM_SEED
    assert RANDOM_SEED == 42


def test_metrics_r2():
    from murkml.evaluate.metrics import r_squared
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert r_squared(y_true, y_pred) == 1.0


def test_metrics_rmse():
    from murkml.evaluate.metrics import rmse
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.0, 2.0, 3.0])
    assert rmse(y_true, y_pred) == 0.0


def test_metrics_kge_perfect():
    from murkml.evaluate.metrics import kge
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert abs(kge(y_true, y_pred) - 1.0) < 1e-10


def test_metrics_percent_bias():
    from murkml.evaluate.metrics import percent_bias
    y_true = np.array([100.0, 200.0, 300.0])
    y_pred = np.array([110.0, 210.0, 310.0])
    assert percent_bias(y_true, y_pred) > 0  # Overprediction


def test_picp():
    from murkml.evaluate.metrics import prediction_interval_coverage
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_lower = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
    y_upper = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    assert prediction_interval_coverage(y_true, y_lower, y_upper) == 1.0


def test_seasonality():
    import pandas as pd
    from murkml.data.features import add_seasonality
    df = pd.DataFrame({
        "sample_time": pd.to_datetime(["2024-01-01", "2024-07-01"]),
        "value": [1.0, 2.0],
    })
    result = add_seasonality(df)
    assert "doy_sin" in result.columns
    assert "doy_cos" in result.columns
    # January should have different seasonality than July
    assert result["doy_sin"].iloc[0] != result["doy_sin"].iloc[1]


def test_qc_filter_empty():
    import pandas as pd
    from murkml.data.qc import filter_continuous
    df = pd.DataFrame()
    filtered, stats = filter_continuous(df)
    assert len(filtered) == 0
