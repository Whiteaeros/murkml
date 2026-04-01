# Dr. Ananya Krishnamurthy — NTU Data Reality Review

**Background:** 12 years applied environmental statistics. Specialty in observational study design, sample size analysis, confounding, and bias diagnostics in environmental monitoring datasets.

**Date:** 2026-03-30

---

## Question 1: Is the 3,646-sample expansion worth the complexity?

No. The cost-benefit arithmetic does not favor this.

You gain 3,646 rows — a 16% expansion — but every single one of those rows is missing 3 of 6 turbidity features (`turbidity_max_1hr`, `turbidity_std_1hr`, `turbidity_instant_alt`). That is not a 16% expansion of *information*. It is a 16% expansion of *row count* with roughly 50% of the turbidity feature space masked. The effective information gain is far smaller than 16%.

Meanwhile, you pay real complexity costs:
- A new `sensor_type` categorical that the model must learn to route on, with a heavily imbalanced split (~86% FNU, ~14% NTU).
- The `turbidity_instant_alt` column will be NaN for 100% of NTU rows AND for most FNU rows (since alt readings are rare), making it nearly uninformative.
- Every downstream validation, feature importance analysis, and ablation study now has to account for this sensor-type stratification or risk conflating effects.

The complexity is not justified by the information content.

## Question 2: Is temporal bias a concern?

Yes, and it is a serious one that I think is being underweighted.

The NTU data spans 1976-2005. The FNU data starts 2006+. These are not overlapping populations — they are separated by a hard temporal boundary that coincides with:

- **Land use change.** Thirty years of urbanization, agricultural practice shifts, BMP adoption, and riparian restoration have altered sediment delivery in most U.S. watersheds. The NLCD changed classification systems between these periods.
- **Climate non-stationarity.** Precipitation intensity distributions have shifted measurably since the 1990s, particularly in the rain-snow transition zones relevant to your Idaho focus.
- **Sampling protocol changes.** USGS revised field methods (equal-width-increment vs. grab), preservation protocols, and lab analytical methods across this boundary. The 2004 TM you cite was itself a response to recognized inconsistencies.
- **Instrument calibration.** Pre-2004 NTU field instruments (Hach 2100P, etc.) had different calibration standards (formazin vs. StablCal), different path lengths, and different response curves than the instruments used in late-period measurements.

You cannot treat 1985 NTU-SSC pairs and 2015 FNU-SSC pairs as exchangeable samples from the same data-generating process. They are not. The confounding between sensor type and time period is *total* — you have zero overlap. The model cannot distinguish "this SSC is different because NTU measures differently" from "this SSC is different because the watershed was different 30 years ago." The `sensor_type` flag will absorb both effects, learning an uninterpretable composite.

## Question 3: Will NaN-heavy rows dilute the signal from complete FNU rows?

Yes, through a specific mechanism that deserves attention.

CatBoost handles NaN natively by learning split directions for missing values. This is fine when missingness is *random* — the model learns that "missing" is uninformative and routes accordingly. But here, missingness is *perfectly correlated with sensor type and era*. Every NTU row is missing the same three features. Every FNU row has them.

This means the model will learn that `turbidity_max_1hr = NaN` is a near-perfect proxy for "this is an NTU sample from 1976-2005." The window statistics cease to be turbidity variability features and become era/sensor indicators. This is a form of information leakage that will distort feature importance rankings and could cause the model to rely less on window statistics for FNU rows as well, since the learned splits now have to accommodate a population where those features are meaningless.

The 3,646 NaN-heavy rows are not neutral. They actively reshape how the model uses the turbidity feature space.

## Question 4: Will adding USGS NTU training samples reduce the +66% bias on external NTU data?

Probably not in a reliable way, and the mechanism matters.

The +66% overprediction on external NTU data has two potential sources:
1. **Measurement scale difference.** NTU and FNU diverge at low turbidities and in colored waters. The model, trained on FNU, systematically misinterprets NTU readings.
2. **Site/context difference.** External sites are non-USGS, with different watershed characteristics, sampling protocols, and SSC lab methods.

Adding 3,646 USGS NTU samples addresses source (1) partially — the model sees some NTU-SSC pairs and may learn a different turbidity-SSC slope for NTU. But because the NTU-SSC pairs are confounded with a different era (source 2 in a temporal sense), you cannot cleanly attribute what the model learns. It might learn "NTU readings from 1990 at USGS sites map to SSC this way" — which is not the same as "NTU readings from 2024 at a state agency site map to SSC this way."

What you actually need to reduce the +66% bias is one of:
- Concurrent FNU-NTU readings to learn the measurement conversion (which you have confirmed do not exist).
- A physics-based NTU-to-FNU correction (published relationships exist, e.g., Anderson 2005, but they are site-specific and unreliable below ~50 NTU).
- Site-specific Bayesian adaptation, which you already have working.

The third option is your strongest path, which leads to Question 5.

## Question 5: Is Bayesian adaptation with 10 samples a simpler path?

Yes, and it is not just simpler — it is statistically better justified.

The Bayesian adaptation approach (10 calibration samples yielding R^2 = 0.43) has a critical advantage: it learns the correction *at the target site, in the target era, with the target instrument.* It does not need to disentangle sensor type from era from watershed change. It just observes "at this site, the model's FNU-trained prediction overshoots NTU-based reality by X" and corrects accordingly.

R^2 = 0.43 from 10 samples is a reasonable starting point. With 20-30 samples you will likely reach R^2 = 0.55-0.65, which is competitive with what the NTU training integration could achieve but without the confounding risks.

I would invest effort in characterizing the adaptation curve more carefully:
- How does R^2 scale with calibration sample count (10, 20, 30, 50)?
- Is the bias correction stable across the turbidity range, or does it break down at extremes?
- Can you stratify by turbidity magnitude (low NTU vs. high NTU) and show the adaptation handles both?

This gives you a *defensible, publishable* story: "Our model transfers to NTU sensors via lightweight Bayesian site adaptation" — which is actually a stronger scientific contribution than "we mixed NTU and FNU data and hoped the model would sort it out."

## Question 6: Recommendation

**Option B. Skip NTU integration.**

My reasoning, in order of importance:

1. **Total confounding.** Sensor type and era have zero overlap. You cannot learn one without learning the other. Any `sensor_type` coefficient is uninterpretable.

2. **The value proposition collapsed.** The original plan — learn FNU-NTU conversion from concurrent readings — was sound. That plan is dead. What remains (3,646 historical grab samples) is a fundamentally different and weaker proposition.

3. **Bayesian adaptation already works.** R^2 = 0.43 from 10 samples, with a clear path to improvement by adding more calibration points. This is cleaner, more defensible, and more useful to practitioners who actually have NTU sensors in the field.

4. **Opportunity cost.** Every hour spent on NTU integration, validation, and debugging is an hour not spent on characterizing the adaptation curve, expanding to more sites, or writing the paper.

5. **Publication risk.** A reviewer will immediately notice the temporal confound. "You added data from a different era measured with a different instrument and claim the model learned a sensor correction" is a paragraph that writes itself in a rejection letter. The adaptation approach is much harder to attack.

**What I would do instead:**
- Run the adaptation curve experiment (10, 20, 30, 50 calibration samples) on external NTU sites.
- Report the zero-shot +66% bias honestly — it demonstrates the FNU-NTU measurement gap is real and quantifiable.
- Show that lightweight adaptation resolves it — this is the publishable result.
- Archive the 3,646 NTU-SSC pairs for potential future use if concurrent FNU-NTU data ever becomes available from a research campaign.

The data is not worthless. It is just not useful *for this model, at this stage, given the confounding structure.* Do not force it.
