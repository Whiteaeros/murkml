# Dual BCF Strategy — Mean-Optimal vs Median-Optimal

## The Problem

The Snowdon BCF corrects for back-transformation bias (Box-Cox → native space). A single global BCF cannot simultaneously optimize the mean AND the median because SSC distributions are right-skewed.

| BCF | NSE | MAPE | Within-2x | Mean Bias | Median Pred/Obs |
|---|---|---|---|---|---|
| Current (1.348) | **0.692** | 55.6% | 65.4% | +2.0% | 1.44x |
| No BCF (1.000) | 0.632 | 37.0% | 73.0% | -24.4% | 1.07x |
| Mean-optimal (1.323) | 0.691 | 53.7% | 66.6% | **0.0%** | 1.41x |
| Median-optimal (0.937) | 0.611 | **36.0%** | **73.8%** | -29.2% | **1.00x** |

## Why This Happens

SSC is right-skewed (a few very large events dominate the mean). The BCF inflates ALL predictions to get the heavy-tail mean right. This makes the typical (median) prediction ~44% too high, even though the mean is correct.

- **Mean-optimal BCF** (Snowdon): multiplies everything by ~1.32. Gets the AVERAGE right. Overpredicts most individual samples. Good for: annual sediment load calculations where the total mass matters.
- **Median-optimal BCF**: multiplies everything by ~0.94. Gets the TYPICAL prediction right. Underpredicts the mean (misses big events). Good for: individual sample predictions, permit compliance, real-time monitoring.

## The Solution: Report Both

Store two BCF values in model metadata:

```json
{
  "bcf_mean": 1.323,
  "bcf_median": 0.937,
  "bcf_method": "snowdon_dual"
}
```

At prediction time:
- **For load estimation:** `pred_native = inverse_transform(pred_ms) * bcf_mean`
- **For individual predictions:** `pred_native = inverse_transform(pred_ms) * bcf_median`

Default to `bcf_median` for most users (individual predictions are the common case). Use `bcf_mean` for load calculations.

## Paper Framing

"We provide two bias correction factors reflecting the fundamental tradeoff between mean-unbiased prediction (for load estimation) and median-unbiased prediction (for individual samples). The Snowdon BCF (1.32) ensures unbiased mean SSC for sediment budget calculations. The median-optimal BCF (0.94) provides the most accurate typical prediction, improving MAPE from 55.6% to 36.0% and within-2x accuracy from 65.4% to 73.8%."

## Implementation

In `train_tiered.py` final model section:
1. Compute Snowdon BCF as before → `bcf_mean`
2. Compute median-optimal BCF from training predictions → `bcf_median`
3. Store both in meta.json

In `evaluate_model.py`:
1. Load both BCF values
2. Default to `bcf_median` for per-reading and per-site metrics
3. Also report metrics with `bcf_mean` for load-estimation context
4. Bayesian adaptation should use `bcf_median` (adapts individual predictions)

In product/deployment:
1. User selects mode: "monitoring" (bcf_median) or "load estimation" (bcf_mean)
2. Default: monitoring mode
3. CQR intervals computed using median BCF (tighter, more honest)

## Impact on Existing Results

All previously reported metrics used bcf_mean (Snowdon). With bcf_median:
- MAPE improves dramatically (55.6% → 36.0%)
- Within-2x improves (65.4% → 73.8%)
- NSE drops (0.692 → 0.611) because NSE is mean-sensitive
- The model looks "worse" on NSE but "better" on every user-facing metric

This is not a model change — it's a reporting choice. Same model, same predictions in model space, just a different scaling constant.
