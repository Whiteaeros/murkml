# Chen Final Review: Bug Fix Verification (2026-03-16)

**Reviewer:** Dr. Sarah Chen, ML Engineer
**Scope:** Verify fixes for 1 HIGH + 3 MEDIUM issues from Round 1-3 review
**Files reviewed:** `attributes.py`, `discrete.py` (post-fix versions)

---

## Finding 1 — HIGH: TDS not viable (16 sites)

**Verdict: FIXED**

TDS is explicitly dropped from MVP in the module docstring (lines 12-14 of `discrete.py`): "TDS dropped from MVP — only 16 sites with >=20 pairable samples... TDS will be evaluated separately as a SC-linear validation target since SC->TDS is near-linear (R^2>0.95)." The `load_discrete_param` still supports TDS mechanically (correct — keeps the door open for future validation work), but it is no longer listed as a core parameter. The param-specific default DL for `tds_evaporative` (5.0 mg/L) is present, which is fine for the eventual SC-linear check.

## Finding 2 — MEDIUM: target_patterns substring match on "value"

**Verdict: FIXED**

The old code used substring matching that would incorrectly exclude any sensor column containing "value". Lines 133-146 of `attributes.py` now use an explicit `exclude_cols` set with every known target/metadata column enumerated. The comment at line 133 correctly attributes the rationale. The set includes all current parameter target columns (ssc, tp, nitrate, tds, orthop, do) plus the generic "value"/"value_log1p". No substring matching remains.

## Finding 3 — MEDIUM: DL/2 can produce 0

**Verdict: FIXED**

Line 178 of `discrete.py`: `dl_values = dl_values.where(dl_values > 0, default_dl)` replaces any zero (or negative) DL with the parameter-specific default before the `/2.0` division at line 182. This guarantees DL/2 > 0 for all non-detect substitutions. The guard is correctly placed after the `fillna` from `Result_Measure` (line 174-175) and before the final `fillna(default_dl)` fallback (line 180), so the chain is: per-record DL -> fill from result value -> replace zeros -> fill remaining NaN -> divide by 2.

## Finding 4 — MEDIUM: Ice/Mnt buffer TODO

**Verdict: FIXED (acknowledged, not blocking)**

This was flagged as a non-blocking TODO for Phase 4 hydrologic event handling. The `hydro_event` column is preserved through the pipeline (lines 187-189) and available for downstream filtering. No code regression. Acceptable for MVP.

---

## Additional Observations (no action required)

- **Tier B-restricted** (lines 218-231 of `attributes.py`): Patel's request for an unconfounded B-vs-C comparison is cleanly implemented. Good addition.
- **Parameter-specific DL defaults** (lines 140-148 of `discrete.py`): Rivera's fix for nutrient DLs is in place with sensible values (TP=0.01, nitrate=0.04, orthoP=0.005).
- The `exclude_cols` set in `attributes.py` includes forward-looking entries (`do_value`, `do_log1p`) for dissolved oxygen, which is not yet an MVP target. This is harmless and avoids a future bug.

---

## Overall Verdict: PASS

All four findings are resolved. No regressions detected. Code is ready to proceed to Phase 4.
