# LSTM Nutrient Prediction Plan

## Context

CatBoost cross-site models achieve R²=0.80 for SSC (sediment) but R²=-0.72 for nitrate — a total failure. The hypothesis: nutrient concentrations are governed by complex temporal and spatial processes that a single-snapshot model cannot capture. An LSTM (sequence model) seeing days/weeks of continuous sensor data could learn the temporal dynamics of nutrient transport that CatBoost misses.

**This is uncharted territory.** No published work uses deep learning with continuous in-situ sensor sequences to predict dissolved nutrients (nitrate, phosphorus) cross-site. Wei Zhi's group (Penn State) has done LSTM for DO and temperature but not nutrients. A successful result — even modest improvement over CatBoost — would be a significant contribution.

**The dream (long-term):** A multi-modal model that processes spatial raster data (land use maps, satellite imagery) alongside temporal sensor sequences and static watershed attributes, enabling nutrient prediction at truly ungauged sites. This plan focuses on the achievable first stage.

---

## Resolved Decisions

| Decision | Resolution |
|---|---|
| Target sites | **Level A** first (sites with continuous sensors). Level B (gauge-only) later. Level C (truly ungauged) is the dream. |
| Why CatBoost fails | **Both** — temporal patterns in existing sensors + missing input data about watershed drivers |
| Target parameters | **TP + nitrate simultaneously** (multi-target) |
| Staging | LSTM on existing sensor data first. Spatial rasters are long-term. |
| Compute | **8GB NVIDIA GPU** available locally. PyTorch not yet installed. |
| Relation to CatBoost work | **Separate project/paper.** Start after CatBoost work wraps up. |

## Open Questions (for expert panel)

1. **Lookback window:** 12 hours (48 steps) vs 7 days (672 steps) vs 30 days. Tradeoff between capturing slow nutrient dynamics and training feasibility. Should longer-term context be passed as summary features alongside the sequence?
2. **Pre-training strategy:** Next-step prediction vs masked reconstruction vs contrastive learning. Masked reconstruction may learn richer cross-sensor relationships.
3. **Multi-target architecture:** Shared LSTM backbone with parameter-specific heads vs prediction chain (SSC→TP) vs fully separate models.
4. **What additional data sources** could improve nutrient prediction at Level A sites? Point source discharge permits (NPDES), fertilizer application timing databases, MODIS vegetation indices?

---

## Implementation Plan

### Step 1: Install PyTorch + CUDA

Add PyTorch with CUDA support to the murkml environment.

```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Update `pyproject.toml` with optional `[neural]` dependency group.

### Step 2: Build Sequence Dataset (`src/murkml/data/sequences.py`)

**New module.** Extracts temporal windows from continuous data for each paired sample.

**Input:** Paired sample time + site_id → look up continuous parquet files
**Output:** `(n_samples, n_timesteps, n_channels)` tensor + target values + site IDs

For each paired sample at time T:
1. Load all 6 continuous sensor channels for that site
2. Extract readings from `T - lookback_window` to `T`
3. Resample to regular 15-min grid (forward-fill small gaps, flag large gaps)
4. Return as a 3D numpy array

**Reuse:** `fetch.py` (data loading patterns), `qc.py` (filtering), `discrete.py` (sample loading)

**Handle missing data:** Some sites don't have all 6 sensors. Options: zero-fill missing channels with a binary mask, or require minimum sensor availability.

**Key files:**
- Create: `src/murkml/data/sequences.py`
- Read from: `data/continuous/{site_id}/{param_code}/*.parquet`
- Read from: `data/processed/nitrate_nitrite_paired.parquet`, `total_phosphorus_paired.parquet`

### Step 3: Build Multi-Target Dataset

Identify sites that have **both** TP and nitrate paired samples. Align timestamps where both parameters were measured simultaneously (or near-simultaneously). For samples where only one parameter is available, use a masked loss that only penalizes the available target.

**Key question:** How many sites have both TP and nitrate with temporal overlap? Need to audit this.

### Step 4: Self-Supervised Pre-Training (`scripts/pretrain_lstm.py`)

Train the LSTM encoder on **all** continuous sensor data (~30M timesteps, 124 sites) without any lab labels.

**Task (TBD — panel decision):** Default to next-step prediction unless panel recommends otherwise.

**Architecture:**
```
Input: (batch, n_timesteps, 6) — 6 sensor channels
  → LSTM encoder (2 layers, 128-256 hidden)
  → Output: predicted next timestep (6 values)
```

**Data:** Load all continuous parquet files, chunk into overlapping windows, shuffle across sites. No paired samples needed.

**Save:** Pre-trained encoder weights as `.pt` file.

**Reuse:** `qc.py` (filter before pre-training)

### Step 5: Fine-Tune for Nutrient Prediction (`src/murkml/models/lstm.py`)

**New module.** Load pre-trained encoder, add prediction head, fine-tune on paired samples.

**Architecture:**
```
Pre-trained LSTM encoder (frozen or low LR)
  → Final hidden state (256-dim vector)
  → Concatenate with static features:
      - GAGES-II pruned attributes (25 features, from attributes.py)
      - Basic site attributes (drainage area, elevation, HUC)
      - Seasonality (doy_sin, doy_cos)
  → Dense layers (256 → 128 → n_targets)
  → Output: log(TP), log(nitrate)
```

**Loss:** MSE on log-transformed targets. Masked for missing parameters (if a sample only has TP, don't penalize the nitrate head).

**Training:**
- LOGO-CV (same as CatBoost — hold out one site at a time)
- Early stopping on validation loss
- AdamW optimizer, learning rate scheduling

**Reuse:** `attributes.py` (GAGES-II loading + pruning), `baseline.py` (LOGO-CV pattern), `metrics.py` (R², KGE, RMSE evaluation)

### Step 6: Training Script (`scripts/train_lstm.py`)

End-to-end training script:
1. Load sequence dataset
2. Load pre-trained encoder
3. Run LOGO-CV
4. Log per-site metrics
5. Save results to `data/results/lstm_comparison.parquet`
6. Compare with CatBoost baselines

### Step 7: Evaluation & Comparison

Use existing metrics from `src/murkml/evaluate/metrics.py`:
- R² (log and natural scale)
- KGE
- RMSE
- Per-site scatter plots
- SHAP-equivalent: attention weights or gradient-based attribution

Compare directly against CatBoost Tier C results for TP and nitrate.

---

## Files to Create

| File | Purpose |
|---|---|
| `src/murkml/data/sequences.py` | Sequence extraction from continuous data |
| `src/murkml/models/lstm.py` | LSTM architecture + training loop |
| `scripts/pretrain_lstm.py` | Self-supervised pre-training on all continuous data |
| `scripts/train_lstm.py` | Fine-tuning + LOGO-CV evaluation |
| `tests/test_sequences.py` | Test sequence extraction, padding, masking |

## Files to Reuse (not modify)

| File | What we reuse |
|---|---|
| `src/murkml/data/qc.py` | QC filtering for continuous data |
| `src/murkml/data/fetch.py` | Data loading patterns |
| `src/murkml/data/discrete.py` | Discrete sample loading |
| `src/murkml/data/attributes.py` | GAGES-II pruning + tier building |
| `src/murkml/evaluate/metrics.py` | R², KGE, RMSE, percent bias |
| `src/murkml/models/baseline.py` | LOGO-CV pattern reference |

---

## Verification

1. **Sequence extraction test:** Load a known site, extract a sequence at a known time, verify values match raw parquet data
2. **Pre-training convergence:** Next-step prediction loss should decrease over epochs. Sanity check: model can reconstruct diurnal temperature cycles
3. **Fine-tuning smoke test:** Train on 5 sites, test on 1. Verify predictions are non-negative and in a reasonable range.
4. **LOGO-CV comparison:** Run full cross-validation, compare median R² and KGE against CatBoost Tier C results from `RESULTS_LOG.md`
5. **Ablation tests:**
   - LSTM without pre-training vs with pre-training
   - LSTM without GAGES-II vs with GAGES-II
   - Different lookback windows (if panel hasn't decided)

---

## Long-Term Vision (The Dream)

Eventually evolve into a multi-modal model:

```
Spatial Branch:     CNN/ViT processing watershed raster data
                    (land use, geology, DEM, NDVI, distance-to-ag)
                         ↓
Temporal Branch:    LSTM processing sensor sequences
                    (turbidity, conductance, DO, pH, temp, discharge)
                         ↓
                    Concatenate → Dense → Nutrient predictions

Level A: All branches active (best predictions)
Level B: Spatial + modeled hydrology (no sensors)
Level C: Spatial only (screening-level estimates)
```

Key spatial data sources to investigate:
- NLCD land cover (30m rasters, with upstream distance context)
- NPDES point source permits (locations + discharge volumes)
- MODIS/Sentinel vegetation indices (seasonal crop activity)
- PRISM precipitation (actual rainfall, not just climate normals)
- NHDPlus flow network (upstream connectivity, travel times)

This is a separate planning effort once Stage 1 LSTM results are in.
