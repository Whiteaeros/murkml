"""Pydantic configuration models for murkml.

Validates config/features.yaml at runtime. Does NOT hardcode feature names —
all content comes from YAML. Adding a feature = editing YAML, not Python.

Usage:
    from murkml.config import load_config
    config = load_config(Path("config/features.yaml"))
    features = config.features.all_features  # ordered list for CatBoost
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class CatBoostConfig(BaseModel):
    """CatBoost hyperparameters."""
    depth: int = Field(ge=1, le=16)
    learning_rate: float = Field(gt=0, le=1)
    l2_leaf_reg: float = Field(ge=0)
    iterations: int = Field(ge=1)
    early_stopping_rounds: int = Field(ge=1)
    boosting_type: Literal["Plain", "Ordered"]
    random_seed: int
    thread_count: int = Field(ge=1)


class TransformConfig(BaseModel):
    """Box-Cox transform settings."""
    type: Literal["boxcox"]
    lmbda: float = Field(alias="lambda", ge=0, le=2)

    model_config = ConfigDict(populate_by_name=True)


class USGSUnits(BaseModel):
    """Unit documentation for data boundaries (declarative, not runtime-enforced)."""
    turbidity: str = "FNU"
    discharge: str = "CFS"
    conductance: str = "uS/cm"
    temperature: str = "degC"
    dissolved_oxygen: str = "mg/L"
    ph: str = "standard_units"
    ssc: str = "mg/L"


class FeatureConfig(BaseModel):
    """Feature configuration. Content from YAML, structure validated here.

    The `feature_order` field is THE authoritative column order for CatBoost .fit().
    Grouped fields (sensor, weather, etc.) are for readability + cross-validation.
    """
    model_config = ConfigDict(extra="forbid")

    # Grouped by category (human readability + validation)
    sensor: list[str]
    temporal: list[str]
    weather: list[str] = []
    engineered: list[str] = []
    site: list[str] = []
    land_cover: list[str] = []
    soils: list[str] = []
    hydrology: list[str] = []
    surficial_geology: list[str] = []
    geochemistry: list[str] = []
    anthropogenic: list[str] = []
    sgmc_lithology: list[str] = []
    categoricals: list[str] = []

    # Authoritative ordered list for CatBoost
    feature_order: list[str]

    def _compute_grouped_set(self) -> set[str]:
        """VALIDATION-ONLY. Called by cross-validators, never in production."""
        grouped_list = (
            self.sensor + self.temporal + self.weather + self.engineered +
            self.site + self.land_cover + self.soils + self.hydrology +
            self.surficial_geology + self.geochemistry +
            self.anthropogenic + self.sgmc_lithology + self.categoricals
        )
        if len(grouped_list) != len(set(grouped_list)):
            dupes = [f for f in grouped_list if grouped_list.count(f) > 1]
            raise ValueError(f"Duplicate features in grouped fields: {set(dupes)}")
        return set(grouped_list)

    @property
    def all_features(self) -> list[str]:
        """Authoritative ordered feature list for CatBoost."""
        return list(self.feature_order)

    @property
    def numeric_features(self) -> list[str]:
        """Numeric features in feature_order order."""
        cat_set = set(self.categoricals)
        return [f for f in self.feature_order if f not in cat_set]

    @property
    def cat_feature_indices(self) -> list[int]:
        """Integer indices of categorical features in feature_order."""
        cat_set = set(self.categoricals)
        return [i for i, f in enumerate(self.feature_order) if f in cat_set]

    @model_validator(mode="after")
    def feature_order_matches_groups(self):
        """feature_order and grouped fields must describe EXACTLY the same features."""
        grouped = self._compute_grouped_set()
        ordered = set(self.feature_order)
        in_groups_only = grouped - ordered
        in_order_only = ordered - grouped
        if in_groups_only or in_order_only:
            raise ValueError(
                f"feature_order and grouped fields diverge. "
                f"In groups only: {in_groups_only}. In order only: {in_order_only}."
            )
        return self

    @model_validator(mode="after")
    def no_duplicates_in_order(self):
        """No duplicates in feature_order."""
        dupes = [f for f in self.feature_order if self.feature_order.count(f) > 1]
        if dupes:
            raise ValueError(f"Duplicate features in feature_order: {set(dupes)}")
        return self


class ModelConfig(BaseModel):
    """Top-level model configuration."""
    version: str
    features: FeatureConfig
    monotone_constraints: list[str]
    exclude_cols: list[str]
    catboost: CatBoostConfig
    transform: TransformConfig
    units: USGSUnits = USGSUnits()

    @model_validator(mode="after")
    def monotone_constraints_exist(self):
        """Monotone constraints must reference features that exist."""
        missing = set(self.monotone_constraints) - set(self.features.all_features)
        if missing:
            raise ValueError(f"Monotone constraints reference unknown features: {missing}")
        return self

    @model_validator(mode="after")
    def no_excluded_features(self):
        """No feature should also be in exclude_cols."""
        overlap = set(self.features.all_features) & set(self.exclude_cols)
        if overlap:
            raise ValueError(f"Features also in exclude_cols: {overlap}")
        return self


def load_config(path: Path) -> ModelConfig:
    """Load and validate model configuration from YAML."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    # feature_order is top-level in YAML but belongs inside features for Pydantic
    if "feature_order" in raw and "features" in raw:
        raw["features"]["feature_order"] = raw.pop("feature_order")
    config = ModelConfig(**raw)
    logger.info(
        f"Config loaded: version={config.version}, "
        f"{len(config.features.all_features)} features "
        f"({len(config.features.categoricals)} categorical)"
    )
    return config
