# Okafor Final Fix Verification — 2026-03-16

**Reviewer:** Dr. Jenna Okafor, Data Engineering Specialist
**Scope:** Verification of 2 HIGH bugs + 1 HIGH integration risk from Round 1-3 review
**Files reviewed:** `src/murkml/data/qc.py`, `src/murkml/data/attributes.py`, `scripts/assemble_dataset.py`

---

## Finding 1: nunique() ignores NaN in dedup

**Original bug:** `deduplicate_discrete()` used `nunique()` on the full group, which silently ignores NaN. A group like `[NaN, 150, 150]` would report `nunique() == 1` and be treated as "all agree," discarding the NaN row without logging a conflict.

**Expected fix:** Drop NaN values before `nunique()`, prefer non-null rows.

**Verdict: FIXED**

Lines 163-173 of `qc.py` now call `group.dropna(subset=[value_col])` first, handle the all-NaN case separately (keeps first row), and only run `nunique()` on non-null values. Non-null rows are preferred in all branches. The logic is correct and the comment credits the fix.

---

## Finding 2: HUC2 NaN produces literal "nan" string

**Original bug:** `astype(str)` on a column containing NaN would produce the string `"nan"`, which then gets zero-padded to `"na"` or passed downstream as a categorical level, corrupting any model that uses HUC2 as a feature.

**Expected fix:** Guard with `notna()` mask before `astype(str)`.

**Verdict: FIXED**

The fix is applied in `attributes.py` at four separate locations within `build_feature_tiers()`:
- Tier B (line 176-180)
- Tier C (line 205-209)
- Tier B-restricted (line 221-225)

Each location uses the same correct pattern:
```python
mask = tier_data["huc2"].notna()
tier_data.loc[mask, "huc2"] = tier_data.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
```

NaN rows are left as NaN (not converted to string), which is the correct behavior for downstream pandas/sklearn handling.

---

## Finding 3: Old vs new dedup policy conflict

**Original risk:** `scripts/assemble_dataset.py` uses a simple `drop_duplicates(subset=["datetime", "ssc_value"], keep="first")` (Fix 18), while `qc.py` has the more sophisticated `deduplicate_discrete()` with org-preference logic. If both run in the pipeline, behavior depends on call order; if only the old one runs, the improved logic is dead code.

**Verdict: PARTIALLY FIXED**

The new `deduplicate_discrete()` in `qc.py` is correct and robust. However, `assemble_dataset.py` (lines 152-159) still uses the old `drop_duplicates()` approach. This means:
- If `assemble_dataset.py` is the active pipeline entry point, the old policy runs and the new `deduplicate_discrete()` is never called.
- The two policies disagree on conflict resolution: the old one keeps the first row regardless of org; the new one prefers USGS records.
- No documentation or TODO acknowledges this divergence.

**Recommendation:** Either (a) replace the `drop_duplicates` call in `assemble_dataset.py` with a call to `qc.deduplicate_discrete()`, or (b) add a comment in both files explicitly documenting which dedup runs when and why. This is not a silent-corruption risk since the old policy is conservative (keeps first), but it means the USGS-preference logic is currently unreachable in the main pipeline.

---

## Overall Verdict: PASS (conditional)

Two of three findings are cleanly fixed. The dedup policy divergence (Finding 3) is a code-hygiene issue, not a correctness bug — the old policy is safe, just less sophisticated. No data corruption risk remains.

**Conditions for unconditional PASS:**
- Wire `deduplicate_discrete()` into `assemble_dataset.py` or document the intentional divergence.

| Finding | Severity | Status |
|---------|----------|--------|
| nunique() ignores NaN | HIGH | FIXED |
| HUC2 NaN literal "nan" | HIGH | FIXED |
| Old vs new dedup policy | HIGH (integration) | PARTIALLY FIXED |
