# Physics-Guided ML Review -- Dr. Kai Nakamura

**Date:** 2026-03-16
**Reviewer:** Dr. Kai Nakamura (Physics-Guided ML Specialist)
**Project:** murkml -- multi-target water quality estimation system
**System under review:** CatBoost gradient boosting, 57 USGS sites, 16,760 paired samples, leave-one-site-out CV

---

## Question 1: Best Architecture for Encoding Physics Constraints

> Given the constraints identified by Vasquez, what is the best architecture for encoding them? For each type of constraint, recommend: soft penalty in loss function, hard architectural constraint (e.g., non-negative output layer), or differentiable physics module. Explain tradeoffs.

### Constraint-by-Constraint Recommendations

I will address each major constraint type that Vasquez is likely to identify, since her review runs in parallel with mine.

#### 1A. Non-negative concentrations (SSC, TDS, NO3, TP)

**Recommendation: Hard architectural constraint.**

This is the simplest and most important constraint. Concentrations cannot be negative. Period. This is not empirical -- it is definitional.

**Implementation with CatBoost:** Apply `exp()` or `softplus()` transformation to the raw output. Alternatively, train on log-transformed targets (which you may already be doing for SSC, since sediment concentrations are typically log-normal). Log-transformation is the standard approach in sediment transport (Rasmussen et al. 2009, USGS Techniques and Methods 1-D3) and implicitly enforces non-negativity.

**Implementation with neural networks:** Use a softplus activation on the output layer: `y = log(1 + exp(x))`. This is smooth, differentiable, and strictly positive. ReLU works too but has a dead gradient at zero.

**Why NOT a soft penalty:** A penalty term like `lambda * max(0, -y)^2` can still produce negative predictions during inference if the penalty weight is too low. For a constraint that is always true by definition, do not leave room for violation. Hard constraints are simpler and more reliable here.

**Tradeoff:** Essentially none. Log-transformed targets are standard practice. The only consideration is that softplus compresses small values, which can slightly reduce resolution near zero -- but SSC/nutrient concentrations near zero are physically uninteresting anyway.

#### 1B. DO saturation upper bound as f(temperature, pressure) -- Benson & Krause (1984)

**Recommendation: Hard architectural constraint (clamp) for supersaturation limit + soft penalty for the temperature-DO relationship.**

The DO saturation equation from Benson & Krause (1984) is thermodynamic -- it defines the equilibrium dissolved oxygen concentration as a function of temperature and barometric pressure. This is as close to a physical law as you get in water quality.

**Implementation:** Compute `DO_sat(T, P)` using the published equation (it is a simple polynomial in temperature). Then:
- **Hard clamp:** Enforce `DO_predicted <= DO_sat * 1.3` (allowing up to ~130% supersaturation, which occurs during algal blooms and turbulent reaeration). A hard ceiling prevents physically absurd predictions.
- **Soft penalty:** Add a loss term that penalizes `max(0, DO_predicted - DO_sat)^2` with moderate weight. This nudges the model toward undersaturation (the typical condition) without absolutely forbidding supersaturation.

**Why this split approach:** Pure hard constraints at 100% saturation would be wrong -- DO can exceed saturation in highly productive or turbulent waters. But predictions at 200% saturation are never realistic. The hard clamp catches catastrophic errors; the soft penalty encodes the prior that most water is at or below saturation.

**Tradeoff:** You need temperature as an input feature (which you have). The Benson & Krause equation is a simple function -- no complex module needed. The only subtlety is handling pressure, which varies with elevation. For USGS sites, you know the elevation, so this is straightforward.

#### 1C. Conductance-TDS proportionality

**Recommendation: Soft penalty with site-adaptive coefficient.**

The relationship TDS approx. k * SpC (specific conductance) is well-established, where k ranges from 0.55 to 0.75 depending on ionic composition (Hem, 1985, USGS Water-Supply Paper 2254). This is empirical, not thermodynamic -- the proportionality constant depends on the geochemistry of the watershed.

**Implementation:** Add a penalty term:

```
L_cond = lambda_cond * (TDS_pred - k * SpC)^2
```

where `k` can either be:
- Fixed at 0.65 (midrange, safe default)
- Learned per-site as an auxiliary output (adds complexity but improves accuracy)
- Set from a lookup based on geology/region (practical middle ground)

**Why soft, not hard:** The ratio is geology-dependent. Enforcing it as a hard constraint with the wrong k value would force the model to learn something false for watersheds where k deviates from the assumed value. A soft penalty says "stay near this relationship" without absolute enforcement.

**Tradeoff:** Requires tuning one additional hyperparameter (lambda_cond). Start with a moderate value and validate that TDS predictions improve without degrading SSC or other targets.

#### 1D. Sediment-phosphorus co-transport (SSC predicts TP)

**Recommendation: Soft penalty (monotonic tendency), NOT a hard constraint.**

Total phosphorus has both dissolved and particulate fractions. The particulate fraction is correlated with SSC because phosphorus adsorbs to fine sediment particles. But the relationship is highly site-dependent -- it depends on soil mineralogy, land use, and whether the phosphorus source is agricultural runoff vs. point-source effluent.

**Implementation:** Use CatBoost's built-in `monotone_constraints` parameter to enforce that, all else being equal, higher SSC predictions are associated with higher TP predictions (monotonic increasing relationship). This is a "soft" structural constraint in the tree-building algorithm -- it constrains how splits are made without requiring a loss function modification.

**Why monotonic constraint, not a loss penalty:** CatBoost natively supports monotonic constraints (documented at catboost.ai). This is the path of least resistance -- one line of configuration, no custom loss function needed. It encodes the directional relationship (more sediment -> more phosphorus) without specifying the quantitative relationship (which varies by site).

**Tradeoff:** Monotonic constraints can slightly reduce model flexibility. In rare cases where the sediment-phosphorus relationship genuinely inverts (e.g., a site dominated by dissolved phosphorus from wastewater effluent), the constraint could hurt. Validate with and without.

#### 1E. Mass balance / conservation constraints

**Recommendation: Defer to a later version. Not worth the complexity for the MVP.**

Mass balance constraints (e.g., total nitrogen = organic N + ammonia + nitrate + nitrite) are theoretically appealing but practically difficult because:
- You may not be predicting all species in the balance
- Measurement uncertainty in the components can exceed the balance residual
- Enforcing mass balance on predictions from a cross-site model is only meaningful if all species are predicted simultaneously at the same precision

If you do implement it later, the right approach is a **differentiable physics module** -- a layer that predicts species fractions and then sums them, architecturally guaranteeing the sum equals the total. This is the approach used by Shen's group at Penn State for water balance in differentiable hydrology models (Shen, 2023, Nature Reviews Earth & Environment).

**Tradeoff:** High implementation cost, moderate benefit at this stage. Revisit when you have multi-species nitrogen predictions working.

### Summary Table

| Constraint | Type | Method | Complexity | Priority |
|---|---|---|---|---|
| Non-negative concentrations | Definitional | Log-transform targets or softplus output | Trivial | Do now |
| DO <= f(T, P) | Thermodynamic | Hard clamp + soft penalty | Low | Do now |
| SpC-TDS proportionality | Empirical | Soft penalty in loss | Low-Medium | Do with TDS |
| SSC-TP monotonicity | Empirical | CatBoost monotone_constraints | Trivial | Do with TP |
| Mass balance | Conservation law | Differentiable module | High | Defer |

---

## Question 2: Multi-Target Architecture

> For the multi-target prediction problem (predicting SSC, TDS, nitrate, phosphorus, DO simultaneously): shared backbone with multiple heads, prediction chain (SSC feeds into TP model), or independent models with physics coupling? What does the literature say about which works best for correlated environmental targets?

### What the Literature Says

**Demiray & Demir (2025, Earth ArXiv)** conducted the most directly relevant study: multi-task learning for hydrological forecasting across 600+ US basins. Their key finding is that a shared-backbone MTL model with task identifiers achieves accuracy comparable to or slightly better than single-task baselines. The shared representation learns cross-variable structure, but the gains are modest -- not transformative.

**Fang et al. (2024, Frontiers in Water)** tested LSTM for 20 water quality variables across ~500 CONUS catchments. LSTM did not markedly outperform WRTDS. Critically, they used grab-sample data (not continuous sensors) and trained single-task models. They did NOT test multi-task architectures, leaving the multi-target question open for your setting.

**Xie et al. (2022, MDPI Water)** directly tested multi-task learning for water quality prediction and found that jointly predicting correlated parameters improved performance on data-sparse targets, particularly when strong inter-parameter correlations exist.

**Sadler et al. (2024)** demonstrated that physics-guided approaches for DO prediction benefited from temperature as a co-input, which is effectively a lightweight form of multi-target reasoning.

### My Recommendation: Shared Backbone with Multiple Heads (for CatBoost: Multi-Output Wrapper)

For your current CatBoost setup, here is the practical reality:

**CatBoost does not natively support multi-output regression.** Each CatBoost model predicts one target. You have three options:

**Option A: Independent models (current approach, extended)**
Train separate CatBoost models for SSC, TDS, NO3, TP, DO. Use the same feature set for all. No inter-target coupling.

- Pros: Simplest. Each model independently optimizable. Easy to add/remove targets.
- Cons: Throws away inter-parameter correlations. Each model must independently learn relationships that are shared.

**Option B: Prediction chain (cascade)**
Train SSC model first. Feed SSC predictions as an input feature to the TP model. Feed temperature + DO_sat to the DO model. Etc.

- Pros: Explicitly encodes known causal structure (sediment carries phosphorus, temperature controls DO). Simple to implement -- just add a feature column.
- Cons: Error propagation. If SSC predictions are wrong, TP predictions inherit that error. Order-dependent: you must decide the causal graph upfront. Harder to maintain.

**Option C: Shared backbone with multiple heads (requires switching to neural networks)**
A single neural network with a shared hidden representation and separate output heads for each target. All targets share the same learned feature representation.

- Pros: Learns shared structure automatically. Inter-target gradients regularize the shared layers. The literature (Demiray 2025, Xie 2022) supports this approach for correlated environmental targets.
- Cons: Requires switching from CatBoost to PyTorch/TensorFlow. Significant implementation effort. Neural networks are harder to tune. On tabular data with <20K samples, gradient boosting typically outperforms neural networks (Grinsztajn et al., 2022, NeurIPS).

### The Practical Answer for a Solo Developer

**Start with Option A (independent CatBoost models), then add Option B (chain) for the SSC->TP and Temperature->DO links.**

Here is why:

1. **CatBoost on tabular data with <20K samples will almost certainly outperform a neural network.** Grinsztajn et al. (2022) showed this convincingly on 45 benchmark datasets. Your 16,760 samples with heterogeneous features (continuous sensors, categorical site attributes, geological features) is exactly the regime where gradient boosting dominates.

2. **The prediction chain is trivial to implement.** After training the SSC model, generate SSC predictions for all training samples. Add `SSC_predicted` as a feature column for the TP model. Two lines of code. This captures the most important inter-parameter dependency (sediment-phosphorus co-transport) without architectural complexity.

3. **You can validate the chain's value immediately.** Train TP with and without the SSC_predicted feature. If it helps, keep it. If not, drop it. No architectural commitment needed.

4. **Save multi-head neural networks for v2.** If/when you have 50K+ samples and want to explore LSTM or transformer architectures for temporal prediction, multi-task learning becomes the natural architecture. But that is a different project phase.

### Implementation Sketch

```python
# Phase 1: Independent models
model_ssc = CatBoostRegressor(loss_function='RMSE', ...)
model_tds = CatBoostRegressor(loss_function='RMSE', ...)
model_do  = CatBoostRegressor(loss_function='RMSE', ...)

# Phase 2: Add chain links
ssc_predictions = model_ssc.predict(X_train)
X_train_tp = X_train.copy()
X_train_tp['ssc_predicted'] = ssc_predictions
model_tp = CatBoostRegressor(loss_function='RMSE', ...)
model_tp.fit(X_train_tp, y_train_tp)
```

This is the 80/20 solution. You get 80% of the multi-target benefit with 20% of the complexity.

---

## Question 3: How Should Constraint Strength Be Set?

> How should constraint strength be set? Fixed penalty weight, learnable weight, or curriculum (start unconstrained, gradually increase constraint strength)?

### The Problem

When you add a physics penalty to a loss function, the total loss becomes:

```
L_total = L_data + lambda * L_physics
```

If `lambda` is too small, the physics constraint is ignored. If too large, the model overfits to the physics prior and underfits the data. The balance matters.

### What the Literature Says

**Karpatne et al. (2017, PGNN paper):** The original PGNN paper for lake temperature modeling treated lambda as a hyperparameter tuned via cross-validation. They tested a grid of lambda values and selected the one that minimized validation loss. This is the simplest and most reproducible approach.

**Wang et al. (2022, MDPI Entropy):** Showed that for physics-informed neural networks solving PDEs, the loss landscape has gradient imbalance between data and physics terms. Proposed dynamic weight adjustment based on gradient magnitudes to balance the terms during training. Effective but adds significant implementation complexity.

**Lu et al. (2021, NeurIPS):** Characterized failure modes in PINNs and showed that fixed penalty weights can lead to optimization pathology -- the physics loss dominates early training and prevents the network from fitting the data at all. Their recommendation: start with low lambda and increase gradually (curriculum approach).

**Shen (2023, Nature Reviews):** In differentiable hydrology models, physics constraints are embedded in the architecture itself (hard constraints via differentiable equations), avoiding the lambda-tuning problem entirely. This is elegant but requires a fundamentally different architecture.

### My Recommendation: Grid Search on Lambda, with a Curriculum Fallback

**For CatBoost with custom loss functions:** You cannot do curriculum learning because CatBoost trains all trees in a single pass -- there is no "epoch" to schedule over. This actually simplifies things.

**Approach:**
1. Define 2-3 physics penalty terms (DO saturation, SpC-TDS proportionality).
2. For each, define a penalty weight lambda.
3. Run a grid search over lambda values: {0, 0.01, 0.1, 1.0, 10.0}.
4. Select based on leave-one-site-out CV performance on the held-out site.
5. The optimal lambda is the one that minimizes prediction error at unseen sites, not at training sites.

**Why this works for your problem:**
- Cross-site generalization is your evaluation criterion. Physics constraints are most valuable precisely when the model encounters a new site. The right lambda is the one that improves out-of-site predictions.
- With 57 sites and LOSO CV, you have 57 folds. That is enough signal to detect whether a constraint helps or hurts generalization.
- Grid search is simple, reproducible, and does not require any custom training loop.

**Important nuance: CatBoost custom loss functions.** CatBoost supports custom objective functions via the `CatBoostRegressor(loss_function=...)` parameter, but implementing a custom loss requires providing the first and second derivatives (gradient and Hessian). For a combined data + physics loss, you would need:

```python
# Pseudo-code for custom CatBoost objective
def physics_guided_objective(y_pred, y_true):
    # Data loss: squared error
    grad_data = 2 * (y_pred - y_true)
    hess_data = 2.0

    # Physics penalty (e.g., DO > DO_sat)
    violation = max(0, y_pred_do - do_sat)
    grad_physics = 2 * lambda_do * violation
    hess_physics = 2 * lambda_do

    return grad_data + grad_physics, hess_data + hess_physics
```

This is feasible but requires care. An alternative is **post-hoc constraint enforcement**: train CatBoost with its standard loss, then clamp/adjust predictions to satisfy physics. This is simpler and still captures most of the benefit for hard constraints like non-negativity and DO ceiling.

**If you later switch to neural networks:** Use curriculum learning. Start with lambda=0 for the first 20% of epochs (let the network learn the data), then linearly increase lambda to its final value over the next 50% of epochs. This avoids the optimization pathology identified by Lu et al. (2021). Implement with a simple lambda scheduler:

```python
def get_lambda(epoch, max_epochs, lambda_final):
    warmup_end = int(0.2 * max_epochs)
    ramp_end = int(0.7 * max_epochs)
    if epoch < warmup_end:
        return 0.0
    elif epoch < ramp_end:
        return lambda_final * (epoch - warmup_end) / (ramp_end - warmup_end)
    else:
        return lambda_final
```

### Summary

| Setting | Method | When to use |
|---|---|---|
| CatBoost (current) | Grid search lambda via LOSO CV | Now |
| CatBoost (simpler alternative) | Post-hoc clamp/adjustment | Now, for hard constraints |
| Neural network (future) | Curriculum schedule + grid search on lambda_final | v2 |
| Fully differentiable model (future) | Embedded in architecture (no lambda needed) | v3+ |

---

## Question 4: Minimum Viable Physics-Guided Architecture

> What's the minimum viable physics-guided architecture that improves on pure CatBoost for this problem? We're a solo developer -- what's the simplest thing that works?

### The Honest Answer

The simplest physics-guided improvements you can make to CatBoost require **zero architecture changes**. They are configuration and post-processing steps, not a new model.

### Tier 1: Zero-Cost Physics (Do Today)

These require no custom code, no new dependencies, and no architecture changes.

**1. Log-transform SSC targets.**
SSC is log-normally distributed. Training on log(SSC) and exponentiating predictions is standard practice in sediment transport (Rasmussen et al. 2009). This implicitly enforces non-negativity and improves model performance on the heavy-tailed SSC distribution. If you are not already doing this, it is likely the single biggest improvement available.

**2. Add DO_sat as a derived feature.**
Compute DO_sat(T, P) using the Benson & Krause (1984) equation for every observation. Add it as an input feature. Also add `DO_deficit = DO_sat - DO_observed` if you have observed DO. The model now has direct access to the physics without any custom loss function. This is the approach used by Sadler et al. (2024) for physics-guided DO prediction.

```python
# Benson & Krause (1984) DO saturation, simplified for freshwater at 1 atm
# T in Celsius
def do_saturation(T):
    return 14.652 - 0.41022 * T + 0.007991 * T**2 - 0.000077774 * T**3
```

**3. Use CatBoost's monotone_constraints.**
Enforce physically meaningful monotonic relationships directly in the tree-building algorithm:
- Temperature vs. DO: monotone decreasing (higher T -> lower DO_sat -> generally lower DO)
- Turbidity vs. SSC: monotone increasing (more turbidity -> more sediment, on average)
- SpC vs. TDS: monotone increasing (more conductance -> more dissolved solids)

```python
# Example: if feature columns are [turbidity, spC, DO, pH, temp, discharge]
# and targets are SSC, TDS, etc.
model_ssc = CatBoostRegressor(
    monotone_constraints={0: 1},  # turbidity (index 0) monotonic increasing with SSC
    ...
)
model_tds = CatBoostRegressor(
    monotone_constraints={1: 1},  # spC (index 1) monotonic increasing with TDS
    ...
)
```

One line of code per model. Native CatBoost feature. No custom loss needed.

**4. Post-hoc output clipping.**
After prediction, clamp outputs:
- All concentrations: `max(0, prediction)` (if not using log-transform)
- DO: `min(prediction, DO_sat * 1.3)` (physical ceiling)
- SSC: `max(0, prediction)` and consider an upper physical bound based on the maximum observed value in your training set

This is trivially implementable and prevents physically absurd predictions at deployment time.

### Tier 2: Low-Cost Physics (Do This Month)

**5. Feature-engineer the physics.**
Instead of encoding physics in the loss function, encode it in the features. This is the gradient-boosting-native way to inject domain knowledge:

- `DO_sat`: thermodynamic saturation (computed from temperature)
- `DO_pct_sat`: observed DO / DO_sat -- the fraction of saturation
- `SpC_TDS_ratio`: if you have any co-located TDS measurements, compute the empirical ratio
- `log_turbidity`: log-transformed turbidity (linearizes the turbidity-SSC relationship)
- `season_sin`, `season_cos`: encode seasonal cycling for nutrients
- `Q_normalized`: discharge normalized by drainage area (specific discharge) for cross-site comparability

This is the single most impactful thing you can do for cross-site generalization. Physics-derived features that are scale-invariant (ratios, normalized quantities, dimensionless numbers) transfer across sites better than raw sensor values.

**6. Prediction chain for SSC -> TP.**
As described in Question 2. Train SSC model, generate predictions, feed to TP model as a feature. Two lines of code.

### Tier 3: Moderate-Cost Physics (Do Next Quarter)

**7. Custom CatBoost loss with physics penalty.**
Write a custom objective function that combines RMSE with a physics penalty (e.g., DO saturation). Requires implementing gradient and Hessian for the combined loss. Maybe 50-100 lines of code. Test whether it improves on Tier 1+2.

My honest assessment: **Tier 1 + Tier 2 will capture 90% of the benefit of physics-guided ML for this problem.** The custom loss function (Tier 3) adds implementation complexity and debugging difficulty, and may not improve over well-engineered physics features + monotonic constraints + post-hoc clipping. Test Tier 1+2 first and measure the gap.

### What NOT to Do (Yet)

- **Do not switch to a neural network for physics-guided ML.** On your data (16K samples, tabular, heterogeneous features), CatBoost will almost certainly outperform an LSTM or MLP. Grinsztajn et al. (2022, NeurIPS) demonstrated this convincingly. The physics-guided neural network literature (Karpatne et al. 2017, Read et al. 2019) is impressive but was developed for settings where neural networks were already the right architecture (dense spatiotemporal data, process-model pretraining). That is not your setting.

- **Do not implement differentiable physics modules.** Shen (2023) showed these are powerful for hydrology, but they require differentiable process-based equations and end-to-end training in PyTorch. That is a research project, not a feature. Revisit when you have temporal models and a larger dataset.

- **Do not over-invest in physics constraints before you have honest baseline numbers.** The PRODUCT_VISION.md says you are still fixing bugs and need proper evaluation metrics. Get your CatBoost baseline clean first. Then add physics features (Tier 1-2). Then measure the gap. The physics constraints are only valuable if you can measure their impact rigorously.

### Recommended Implementation Order

```
Week 1:  Log-transform targets, add DO_sat feature, add monotonic constraints
         -> Retrain and compare to baseline. Report metrics.

Week 2:  Add physics-derived features (DO_pct_sat, log_turbidity, seasonal encoding)
         Post-hoc output clipping in prediction pipeline.
         -> Retrain and compare. Report metrics.

Week 3:  Implement prediction chain (SSC -> TP, T -> DO).
         -> Compare chained vs. independent. Report metrics.

Week 4+: If gap remains vs. literature, consider custom loss function.
         Otherwise, move to multi-parameter data pull and validation.
```

---

## Key References

- Karpatne, A., Watkins, W., Read, J., & Kumar, V. (2017). Physics-guided Neural Networks (PGNN): An Application in Lake Temperature Modeling. arXiv:1710.11431.
- Read, J. S., et al. (2019). Process-guided deep learning predictions of lake water temperature. Water Resources Research, 55(11), 9173-9190.
- Daw, A., et al. (2020). Physics-Guided Architecture (PGA) of Neural Networks for Quantifying Uncertainty in Lake Temperature Modeling. SIAM SDM 2020.
- Shen, C. (2023). Differentiable modelling to unify machine learning and physical models for geosciences. Nature Reviews Earth & Environment, 4, 552-567.
- Grinsztajn, L., Oyallon, E., & Varoquaux, G. (2022). Why do tree-based models still outperform deep learning on typical tabular data? NeurIPS 2022.
- Fang, K., et al. (2024). Modeling continental US stream water quality using LSTM and WRTDS. Frontiers in Water, 6, 1456647.
- Demiray, B. & Demir, I. (2025). Multi-Task Learning as a Step Toward Building General-Purpose Hydrological Forecasting Systems. Earth ArXiv.
- Rasmussen, P. P., et al. (2009). Guidelines and procedures for computing time-series suspended-sediment concentrations and loads from in-stream turbidity-sensor and streamflow data. USGS Techniques and Methods 3-C4.
- Benson, B. B. & Krause, D. Jr. (1984). The concentration and isotopic fractionation of oxygen dissolved in freshwater and seawater in equilibrium with the atmosphere. Limnology and Oceanography, 29(3), 620-632.
- Hem, J. D. (1985). Study and interpretation of the chemical characteristics of natural water. USGS Water-Supply Paper 2254.
- Lu, L., et al. (2021). Characterizing possible failure modes in physics-informed neural networks. NeurIPS 2021.
- Wang, S., et al. (2022). Dynamic Weight Strategy of Physics-Informed Neural Networks for the 2D Navier-Stokes Equations. Entropy, 24(9), 1254.
- Xie, Z., et al. (2022). Water Quality Prediction Based on Multi-Task Learning. MDPI Water, 14.
- Sadler, J. M., et al. (2024). Physics-guided deep learning for dissolved oxygen prediction. [Cited in project handoff; verify full reference.]
- Lu, C., et al. (2021). Physics-informed neural networks with hard constraints for inverse design. SIAM Journal on Scientific Computing, 43(6), B1105-B1132.

---

## Bottom Line

You are in a better position than you think. CatBoost with physics-derived features, monotonic constraints, and post-hoc clipping IS a physics-guided architecture -- it just does not require a neural network or a custom loss function. The literature on PGNNs is exciting but was built for different data regimes (dense spatiotemporal grids, process-model output as pretraining data). Your regime -- sparse grab samples, tabular features, cross-site transfer -- favors gradient boosting with smart feature engineering.

Do the simple things first. Measure rigorously. Only add complexity when you have evidence it helps. That is how physics-guided ML should work in practice.
