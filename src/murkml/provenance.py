"""Lightweight provenance tracking for murkml pipeline runs.

Records what happened during a pipeline run — row counts at each step,
file checksums, environment info — and writes a JSON manifest to
data/provenance/. No new dependencies: uses stdlib json, hashlib, datetime.

Design principles:
    - Generated, not authored. Manifests are byproducts of running the pipeline.
    - Disposable. Delete and re-run to regenerate.
    - Additive. Each run creates a new manifest file; old ones are kept.

Usage:
    from murkml.provenance import start_run, log_step, log_file, end_run

    start_run("assemble_ssc")
    # ... pipeline code ...
    log_step("qc_filter", site=site_id, rows_in=100, rows_out=85)
    log_file("data/processed/turbidity_ssc_paired.parquet", role="output")
    end_run()
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level state for the current run
_current_run: dict | None = None
_project_root: Path = Path(__file__).resolve().parent.parent.parent  # murkml root


def start_run(run_name: str) -> None:
    """Initialize a new provenance manifest for a pipeline run.

    Args:
        run_name: Short identifier like "assemble_ssc" or "train_tiered".
    """
    global _current_run

    _current_run = {
        "run_id": str(uuid.uuid4()),
        "run_name": run_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "git_commit": _get_git_commit(),
        "environment": _get_environment(),
        "random_seed": 42,
        "steps": [],
        "files": [],
    }
    logger.info(f"Provenance: started run '{run_name}' ({_current_run['run_id'][:8]})")


def log_step(step_name: str, **kwargs) -> None:
    """Record a processing step in the current run manifest.

    Args:
        step_name: Name like "qc_filter", "align", "feature_engineering".
        **kwargs: Any key-value pairs to record (rows_in, rows_out, site_id, etc.)
    """
    if _current_run is None:
        return  # No active run — silently skip (fire-and-forget)

    record = {
        "step": step_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Ensure all values are JSON-serializable
    for k, v in kwargs.items():
        try:
            json.dumps(v)
            record[k] = v
        except (TypeError, ValueError):
            record[k] = str(v)

    _current_run["steps"].append(record)


def log_file(path: str | Path, role: str = "output") -> None:
    """Record a file's provenance in the current run manifest.

    Args:
        path: File path (relative to project root or absolute).
        role: "input" or "output".
    """
    if _current_run is None:
        return

    abs_path = Path(path)
    if not abs_path.is_absolute():
        abs_path = _project_root / path

    if not abs_path.exists():
        logger.warning(f"Provenance: file not found: {path}")
        _current_run["files"].append({
            "path": str(path),
            "role": role,
            "exists": False,
        })
        return

    rel_path = str(path)
    try:
        rel_path = str(abs_path.relative_to(_project_root))
    except ValueError:
        rel_path = str(abs_path)

    record = {
        "path": rel_path,
        "role": role,
        "exists": True,
        "sha256": _file_sha256(abs_path),
        "size_bytes": abs_path.stat().st_size,
    }

    # For parquet files, read metadata without loading the full file
    if abs_path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
            meta = pq.read_metadata(abs_path)
            record["n_rows"] = meta.num_rows
            record["n_cols"] = meta.num_columns
            schema = pq.read_schema(abs_path)
            record["columns"] = schema.names
        except Exception:
            try:
                import pandas as pd
                df = pd.read_parquet(abs_path)
                record["n_rows"] = len(df)
                record["n_cols"] = len(df.columns)
                record["columns"] = list(df.columns)
            except Exception:
                pass  # Can't read parquet metadata — skip

    _current_run["files"].append(record)


def end_run() -> Path | None:
    """Finalize the manifest and write it to data/provenance/.

    Returns:
        Path to the written manifest file, or None if no active run.
    """
    global _current_run

    if _current_run is None:
        logger.warning("Provenance: end_run() called with no active run.")
        return None

    _current_run["finished_at"] = datetime.now(timezone.utc).isoformat()

    # Write manifest
    provenance_dir = _project_root / "data" / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{_current_run['run_name']}_{timestamp}.json"
    manifest_path = provenance_dir / filename

    with open(manifest_path, "w") as f:
        json.dump(_current_run, f, indent=2)

    logger.info(
        f"Provenance: finished run '{_current_run['run_name']}' "
        f"({len(_current_run['steps'])} steps, {len(_current_run['files'])} files) "
        f"→ {manifest_path.name}"
    )

    _current_run = None
    return manifest_path


def _get_git_commit() -> str:
    """Get the current git HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=_project_root,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_environment() -> dict:
    """Capture the runtime environment."""
    env = {
        "python_version": sys.version.split()[0],
        "os": f"{platform.system()} {platform.release()}",
    }
    # Key package versions
    for pkg in ["pandas", "numpy", "catboost", "dataretrieval"]:
        try:
            mod = __import__(pkg)
            env[f"{pkg}_version"] = getattr(mod, "__version__", "unknown")
        except ImportError:
            pass
    return env


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
