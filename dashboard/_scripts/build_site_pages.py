"""
Generate per-site .qmd detail pages for every holdout site.

Run from the dashboard/ directory:
    python _scripts/build_site_pages.py
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


def safe_filename(site_id: str) -> str:
    """Replace characters that are problematic in filenames."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", site_id)


def build_all_site_pages() -> None:
    data_dir = Path("dashboard_data")
    out_dir = Path("sites")
    out_dir.mkdir(exist_ok=True)

    per_site = pd.read_parquet(data_dir / "per_site.parquet")
    per_reading = pd.read_parquet(data_dir / "per_reading.parquet")
    meta = pd.read_parquet(data_dir / "site_metadata.parquet")

    # Only holdout sites
    holdout_meta = meta[meta["role"] == "holdout"]
    holdout_ids = sorted(holdout_meta["site_id"].unique())

    print(f"Generating {len(holdout_ids)} site pages...")

    for site_id in holdout_ids:
        fname = safe_filename(site_id)

        # Gather metadata
        site_meta_row = meta[meta["site_id"] == site_id]
        lat = float(site_meta_row["latitude"].iloc[0]) if len(site_meta_row) > 0 else None
        lon = float(site_meta_row["longitude"].iloc[0]) if len(site_meta_row) > 0 else None
        n_samples = int(site_meta_row["n_samples"].iloc[0]) if len(site_meta_row) > 0 else 0

        # Gather per-site metrics
        site_metrics = per_site[per_site["site_id"] == site_id]
        if len(site_metrics) > 0:
            row = site_metrics.iloc[0]
            nse = row.get("nse_native", float("nan"))
            mape = row.get("mape_pct", float("nan"))
            bias = row.get("bias_pct", float("nan"))
            within_2x = row.get("frac_within_2x", float("nan"))
        else:
            nse = mape = bias = within_2x = float("nan")

        def fmt(val, pct=False):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return "N/A"
            if pct:
                return f"{val:.1f}%"
            return f"{val:.3f}"

        qmd = f"""---
title: "{site_id}"
---

```{{python}}
#| echo: false
from pathlib import Path
import sys
sys.path.insert(0, "..")
```

## Location

- **Latitude:** {fmt(lat)}
- **Longitude:** {fmt(lon)}
- **Role:** Holdout
- **Samples:** {n_samples}

```{{python}}
#| echo: false
#| label: fig-site-map-{fname}
from _scripts.figures import make_site_location_map

fig = make_site_location_map(
    Path("dashboard_data/site_metadata.parquet"),
    "{site_id}",
)
fig.show()
```

## Observed vs Predicted

```{{python}}
#| echo: false
#| label: fig-site-detail-{fname}
from _scripts.figures import make_site_detail

fig = make_site_detail(
    Path("dashboard_data/per_reading.parquet"),
    "{site_id}",
)
fig.show()
```

## Site Metrics

| Metric | Value |
|--------|-------|
| R\u00b2 (NSE) | {fmt(nse)} |
| MAPE | {fmt(mape, pct=True)} |
| Bias | {fmt(bias, pct=True)} |
| Within 2x | {fmt(within_2x)} |
| Samples | {n_samples} |

## Rating Curve

```{{python}}
#| echo: false
#| label: fig-rating-curve-{fname}
from _scripts.figures import make_rating_curve

fig = make_rating_curve(
    Path("dashboard_data/per_reading.parquet"),
    "{site_id}",
)
fig.show()
```

[Back to Site Explorer](../sites.html)
"""
        out_path = out_dir / f"{fname}.qmd"
        out_path.write_text(qmd, encoding="utf-8")

    print(f"Done. Wrote {len(holdout_ids)} .qmd files to {out_dir}/")


if __name__ == "__main__":
    build_all_site_pages()
