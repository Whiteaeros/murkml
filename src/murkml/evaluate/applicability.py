"""Applicability domain detection for murkml models.

Determines whether a new site falls within the model's reliable envelope
before returning predictions. Uses worst-case-governs scoring (Krishnamurthy):
the final score is the minimum across all independent sub-scores, preventing
a catastrophic failure in one dimension from being masked by good scores elsewhere.

Confidence tiers:
    high (≥0.7): Site well-represented in training data
    moderate (≥0.4): Some mismatch, predictions usable with caution
    low (≥0.1): At edge of training domain, screening only
    not_applicable (<0.1): Model fundamentally wrong for this site
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ApplicabilityChecker:
    """Assess whether a site falls within a model's reliable envelope.

    Initialize from model metadata (loaded from _meta.json).
    """

    TIER_THRESHOLDS = {"high": 0.7, "moderate": 0.4, "low": 0.1}

    def __init__(self, meta: dict):
        self.feature_ranges = meta.get("feature_ranges", {})
        self.categorical_values_seen = meta.get("categorical_values_seen", {})
        self.sites_per_ecoregion = meta.get("sites_per_ecoregion", {})
        self.sites_per_geology = meta.get("sites_per_geology", {})
        self.param = meta.get("param", "unknown")
        self.schema_version = meta.get("schema_version", 1)

    def check(
        self,
        site_features: pd.Series | dict,
        site_turbidity: np.ndarray | None = None,
        site_target: np.ndarray | None = None,
    ) -> dict:
        """Evaluate applicability for a single site.

        Args:
            site_features: Feature values for the site (dict or Series).
            site_turbidity: Array of turbidity values (for TP correlation check).
            site_target: Array of target values (for TP correlation check).

        Returns:
            {"tier": str, "score": float, "warnings": list[str],
             "sub_scores": dict[str, float]}
        """
        if isinstance(site_features, dict):
            site_features = pd.Series(site_features)

        sub_scores = {}
        warnings = []

        # Check 1: Categorical coverage (0 or 1)
        sub_scores["categorical_coverage"] = self._check_categorical_coverage(
            site_features, warnings
        )

        # Check 2: Regime density (0-1)
        sub_scores["regime_density"] = self._check_regime_density(
            site_features, warnings
        )

        # Check 3: Feature ranges (0-1)
        sub_scores["feature_ranges"] = self._check_feature_ranges(
            site_features, warnings
        )

        # Check 4: TP correlation (TP only, 0-1)
        if self.param == "total_phosphorus" and site_turbidity is not None and site_target is not None:
            sub_scores["tp_correlation"] = self._check_tp_correlation(
                site_turbidity, site_target, warnings
            )

        # Final score = minimum of all sub-scores (worst-case-governs)
        score = min(sub_scores.values()) if sub_scores else 0.0

        # Map to tier
        tier = "not_applicable"
        for tier_name, threshold in sorted(
            self.TIER_THRESHOLDS.items(), key=lambda x: -x[1]
        ):
            if score >= threshold:
                tier = tier_name
                break

        return {
            "tier": tier,
            "score": round(score, 3),
            "warnings": warnings,
            "sub_scores": {k: round(v, 3) for k, v in sub_scores.items()},
        }

    def _check_categorical_coverage(
        self, features: pd.Series, warnings: list[str]
    ) -> float:
        """Check if categorical feature values were seen in training."""
        if not self.categorical_values_seen:
            return 1.0  # No categoricals to check

        scores = []
        for col, seen_values in self.categorical_values_seen.items():
            val = features.get(col)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                val = "missing"
            if str(val) in [str(v) for v in seen_values] or str(val) == "missing":
                scores.append(1.0)
            else:
                scores.append(0.0)
                warnings.append(f"Unknown {col}='{val}' (not in training data)")

        return min(scores) if scores else 1.0

    def _check_regime_density(
        self, features: pd.Series, warnings: list[str]
    ) -> float:
        """Check how many training sites share this site's regime."""
        scores = []

        ecoregion = features.get("ecoregion")
        if ecoregion and self.sites_per_ecoregion:
            n_sites = self.sites_per_ecoregion.get(str(ecoregion), 0)
            score = min(n_sites / 5.0, 1.0)
            scores.append(score)
            if n_sites < 3:
                warnings.append(
                    f"Sparse ecoregion '{ecoregion}': only {n_sites} training sites"
                )

        geol = features.get("geol_class")
        if geol and self.sites_per_geology:
            n_sites = self.sites_per_geology.get(str(geol), 0)
            score = min(n_sites / 5.0, 1.0)
            scores.append(score)
            if n_sites < 3:
                warnings.append(
                    f"Sparse geology '{geol}': only {n_sites} training sites"
                )

        return min(scores) if scores else 1.0

    def _check_feature_ranges(
        self, features: pd.Series, warnings: list[str]
    ) -> float:
        """Check what fraction of numeric features are within training range."""
        if not self.feature_ranges:
            return 1.0

        in_range = 0
        total = 0
        out_of_range_features = []

        for col, bounds in self.feature_ranges.items():
            val = features.get(col)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue

            total += 1
            fmin = bounds["min"]
            fmax = bounds["max"]
            margin = (fmax - fmin) * 0.1  # 10% margin

            if fmin - margin <= val <= fmax + margin:
                in_range += 1
            else:
                out_of_range_features.append(col)

        if total == 0:
            return 1.0

        score = in_range / total

        if out_of_range_features:
            warnings.append(
                f"Features outside training range: {', '.join(out_of_range_features[:5])}"
            )

        return score

    def _check_tp_correlation(
        self,
        turbidity: np.ndarray,
        target: np.ndarray,
        warnings: list[str],
    ) -> float:
        """Check turbidity-TP correlation (dissolved-P flag)."""
        turbidity = np.asarray(turbidity)
        target = np.asarray(target)

        valid = ~(np.isnan(turbidity) | np.isnan(target))
        if valid.sum() < 10:
            warnings.append("Too few paired turbidity-TP samples for correlation check")
            return 0.5  # Uncertain, not a failure

        corr = np.corrcoef(turbidity[valid], target[valid])[0, 1]
        score = max(0.0, corr / 0.5)  # 0.5 correlation = score 1.0
        score = min(score, 1.0)

        if corr < 0.3:
            warnings.append(
                f"Low turbidity-TP correlation ({corr:.2f}): likely dissolved-P dominated"
            )

        return score
